"""External engines as ordinary games: OpenSpiel and Gymnasium adapters.

The lab never re-implements a rulebook that a solid engine already ships.
Instead a thin adapter class turns the engine into a
:class:`~strategy_lab.core.game.Game`, so every view, bot, lens and test
works on it unchanged.

====================  ======================================================
:class:`SpielGame`    any game of the ``pyspiel`` wheel (chess, backgammon,
                      Kuhn poker, Skat, our own Python Doppelkopf, ...)
:class:`GymGame`      any single-agent Gymnasium environment with discrete
                      actions (CartPole, ...)
====================  ======================================================

OpenSpiel
---------
The state *is* the engine's ``pyspiel.State``. The adapter maps the lab's
OpenSpiel-shaped API one to one:

* ``copy_state`` is ``state.clone()`` (deepcopy of engine objects is slow),
* ``move`` is ``apply_action(int(a))``, so a replayed log gives the same
  state (OpenSpiel is deterministic once chance outcomes are fixed),
* chance nodes are the engine's own explicit chance nodes (pyspiel uses the
  player id ``-1``, the same value as :data:`~strategy_lab.core.game.CHANCE`),
* ``key`` is the action history, which identifies a state exactly,
* ``observation`` is the information state string (or the observation
  string if the game has none): only what that seat knows.

Games with hidden information must not put ``str(state)`` into a scene,
because OpenSpiel prints every hand there. :meth:`SpielGame.scene` renders
the viewer's observation instead.

Bots: :class:`MCTSPolicy` wraps OpenSpiel's MCTS with a random-rollout
evaluator. It builds a fresh ``MCTSBot`` per decision, seeded from the
caller's ``rng``, so the same position and the same seed always give the same
move. For imperfect-information games it uses *determinization* (PIMC): sample
a world that matches what the seat knows, search it, and add up the visit
counts over several worlds. That never reads hidden cards of other seats.

Privacy
-------
The move log may show every step to a spectator but must hide a dealt card
from the other seats (:meth:`~strategy_lab.core.game.Game.privacy`).
:meth:`SpielGame.privacy` derives the audience of a chance step from the
engine: the seats whose observation string changes. Games whose observation
does not change during the deal (Skat) override it.

Gymnasium
---------
:class:`GymGame` has one player and no opponent. Its randomness is one
*seed-as-outcome* chance node at the start: the outcome is a 31-bit seed fed
to ``env.reset(seed=...)``. Gymnasium environments are deterministic given
that seed and the actions, so the action log replays exactly. Copying a state
deep-copies the environment (about 70 microseconds for CartPole), which is
faster than rebuilding it from the log and works for any env that can be
copied.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, ClassVar

import pyspiel

from strategy_lab.core import CHANCE, Game, Policy, scene
from strategy_lab.core.game import Action

#: Upper bound (exclusive) of seeds drawn by seed-as-outcome chance nodes.
SEED_LIMIT = 2 ** 31


# --------------------------------------------------------------------------- #
# MCTS bot
# --------------------------------------------------------------------------- #
class MCTSPolicy(Policy):
    """OpenSpiel's MCTS with random rollouts, deterministic per decision.

    Args:
        simulations: tree-search simulations per decision (per world).
        uct_c: exploration constant of UCT.
        rollouts: random rollouts that evaluate each new leaf.
        worlds: determinized worlds searched for hidden-information games
            (the visit counts of all worlds are added up).
        solve: let the search prove won and lost positions (finds mates).
        name: shown in match results.
    """

    def __init__(self, simulations: int = 100, uct_c: float = 2.0, rollouts: int = 1,
                 worlds: int = 6, solve: bool = True, name: str = "mcts"):
        self.simulations = simulations
        self.uct_c = uct_c
        self.rollouts = rollouts
        self.worlds = worlds
        self.solve = solve
        self.name = name

    def _search(self, world: pyspiel.State, seed: int) -> dict[int, int]:
        """Visit count of every root action after one search."""
        evaluator = pyspiel.RandomRolloutEvaluator(self.rollouts, seed)
        bot = pyspiel.MCTSBot(world.get_game(), evaluator, self.uct_c, self.simulations,
                              100, self.solve, seed, False)
        root = bot.mcts_search(world)
        return {int(c.action): int(c.explore_count) for c in root.children}

    def visits(self, game: "SpielGame", s: pyspiel.State, player: int,
               rng: random.Random) -> dict[int, int]:
        """Visit counts per legal action, summed over the searched worlds."""
        total: dict[int, int] = {}
        n = 1 if game.perfect_information else self.worlds
        for _ in range(n):
            world = s if game.perfect_information else game.sample_world(s, player, rng)
            for a, v in self._search(world, rng.randrange(SEED_LIMIT)).items():
                total[a] = total.get(a, 0) + v
        return total

    def act(self, game, s, player, rng):
        legal = game.legal_actions(s)
        if len(legal) == 1:
            return legal[0]
        counts = self.visits(game, s, player, rng)
        best = max(counts.get(a, 0) for a in legal)
        return rng.choice([a for a in legal if counts.get(a, 0) == best])

    def trace(self, game, s, player):
        """The search's opinion: visit share per action (fixed seed)."""
        rng = random.Random(20260710)
        counts = self.visits(game, s, player, rng)
        total = sum(counts.values()) or 1
        shares = {game.action_label(s, a): round(counts.get(a, 0) / total, 3)
                  for a in game.legal_actions(s)}
        return {"policy": self.name, "visit_share": shares}


# --------------------------------------------------------------------------- #
# OpenSpiel
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=None)
def _spiel_traits(name: str) -> dict:
    """Class-level facts of a pyspiel game, read once from its ``GameType``."""
    game = pyspiel.load_game(name)
    gt = game.get_type()
    return {
        "num_players": game.num_players(),
        "perfect_information": gt.information == pyspiel.GameType.Information.PERFECT_INFORMATION,
        "stochastic": gt.chance_mode != pyspiel.GameType.ChanceMode.DETERMINISTIC,
        "simultaneous": gt.dynamics == pyspiel.GameType.Dynamics.SIMULTANEOUS,
        "info_state": bool(gt.provides_information_state_string),
    }


class SpielGame(Game):
    """Base class of every game that runs on an OpenSpiel engine.

    A concrete game sets :attr:`spiel_name` (the short name registered in
    pyspiel), the usual catalog metadata, and overrides presentation:
    :meth:`scene`, :meth:`status`, captions. The class flags
    ``num_players``, ``perfect_information``, ``stochastic`` and
    ``simultaneous`` are read from the engine's ``GameType`` unless the class
    sets them.

    Variant parameters (:class:`~strategy_lab.core.game.Param`) listed in
    :attr:`forward_params` are passed on to the engine as game parameters.
    """

    family_id = "openspiel"
    family_name = "OpenSpiel classics"
    family_blurb = ("Real games on Google DeepMind's OpenSpiel engine. The rules come "
                    "from the engine, so the lab can study them with the same tools "
                    "as any hand-written game: trees, bots, odds and equilibria.")

    #: Short name registered in pyspiel (``"chess"``). Empty on abstract bases.
    spiel_name: ClassVar[str] = ""
    #: Engine parameters that never change (merged under the forwarded ones).
    spiel_params: ClassVar[dict[str, Any]] = {}
    #: Names of :attr:`~strategy_lab.core.game.Game.params` forwarded to the engine.
    forward_params: ClassVar[tuple[str, ...]] = ()
    #: Shown in the status line while a chance node is pending.
    chance_word: ClassVar[str] = "Chance"
    #: ``engine_seats[seat]`` is the engine's player id of a lab seat. Empty means
    #: the identity. The lab wants the first mover in seat 0; OpenSpiel's chess
    #: numbers Black 0 and White 1, so Chess sets ``(1, 0)``.
    engine_seats: ClassVar[tuple[int, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = vars(cls).get("spiel_name")
        if not name:
            return
        traits = _spiel_traits(name)
        for attr in ("num_players", "perfect_information", "stochastic", "simultaneous"):
            if attr not in vars(cls):
                setattr(cls, attr, traits[attr])

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        #: The loaded pyspiel game (shared by every state of this instance).
        self.engine: pyspiel.Game = pyspiel.load_game(self.spiel_name, self.engine_params())

    def engine_params(self) -> dict[str, Any]:
        """Parameters for ``pyspiel.load_game``."""
        out = dict(self.spiel_params)
        out.update({k: self.p[k] for k in self.forward_params})
        return out

    def engine_player(self, seat: int) -> int:
        """The engine's player id of lab seat ``seat``."""
        return self.engine_seats[seat] if self.engine_seats else seat

    def seat_of(self, engine_player: int) -> int:
        """The lab seat of an engine player id (chance and terminal ids pass through)."""
        if engine_player < 0 or not self.engine_seats:
            return engine_player
        return self.engine_seats.index(engine_player)

    # ======================================================================= #
    # Rules: straight delegation to the engine
    # ======================================================================= #
    def initial_state(self) -> pyspiel.State:
        return self.engine.new_initial_state()

    def copy_state(self, s: pyspiel.State) -> pyspiel.State:
        return s.clone()

    def current_player(self, s: pyspiel.State) -> int:
        return self.seat_of(int(s.current_player()))

    def legal_actions(self, s: pyspiel.State) -> list[Action]:
        return [int(a) for a in s.legal_actions()]

    def move(self, s: pyspiel.State, a: Action) -> None:
        s.apply_action(int(a))

    def is_terminal(self, s: pyspiel.State) -> bool:
        return bool(s.is_terminal())

    def returns(self, s: pyspiel.State) -> list[float]:
        r = s.returns()
        return [float(r[self.engine_player(seat)]) for seat in range(self.num_players)]

    def chance_outcomes(self, s: pyspiel.State) -> list[tuple[Action, float]]:
        return [(int(a), float(p)) for a, p in s.chance_outcomes()]

    def key(self, s: pyspiel.State) -> str:
        """The action history: it identifies a state exactly."""
        return s.history_str()

    def observation(self, s: pyspiel.State, player: int) -> str:
        """What ``player`` knows: the information state, else the observation."""
        player = self.engine_player(player)
        if _spiel_traits(self.spiel_name)["info_state"]:
            return s.information_state_string(player)
        return s.observation_string(player)

    # ======================================================================= #
    # Hidden information
    # ======================================================================= #
    def sample_world(self, s: pyspiel.State, player: int, rng: random.Random) -> pyspiel.State:
        """A state that looks exactly like ``s`` from ``player``'s seat (for PIMC bots).

        The default asks the engine to resample from the information state
        (supported by Kuhn poker). Games with hidden cards override this.
        """
        if self.perfect_information:
            return s.clone()
        return s.resample_from_infostate(self.engine_player(player), rng.random)

    def privacy(self, s: pyspiel.State, a: Action, player: int) -> tuple[int, ...] | None:
        """Chance steps are visible to the seats whose observation they change."""
        if player != CHANCE or self.perfect_information:
            return None
        return self.chance_audience(s, a)

    def chance_audience(self, s: pyspiel.State, a: Action) -> tuple[int, ...] | None:
        """Seats that see chance outcome ``a``; ``None`` if all of them do.

        Compares each seat's observation string before and after the outcome.
        """
        after = s.clone()
        after.apply_action(int(a))
        changed = tuple(p for p in range(self.num_players)
                        if self.observation(s, p) != self.observation(after, p))
        return None if len(changed) == self.num_players else changed

    def describe_hidden(self, s: pyspiel.State, a: Action, player: int) -> str:
        if player != CHANCE:
            return "makes a hidden move"
        audience = self.privacy(s, a, player)
        if audience and len(audience) == 1:
            return f"deals a card to {self.seat_label(audience[0])}"
        return "deals a card"

    # ======================================================================= #
    # Presentation
    # ======================================================================= #
    def action_label(self, s: pyspiel.State, a: Action) -> str:
        p = s.current_player()      # an engine id: no seat mapping needed here
        return s.action_to_string(p if p >= 0 else CHANCE, int(a))

    def describe_chance(self, s: pyspiel.State, a: Action) -> str:
        return self.action_label(s, a)

    def status(self, s: pyspiel.State, viewer: int | None) -> str:
        if self.is_terminal(s):
            if viewer is None:
                return "Game over"
            return {"win": "Game over: you won", "loss": "Game over: you lost",
                    "draw": "Game over: a draw"}[self.outcome(self.returns(s), viewer)]
        p = self.current_player(s)
        if p == CHANCE:
            return f"{self.chance_word}..."
        if viewer is not None and p == viewer:
            return "Your move"
        return f"{self.seat_label(p)} to move"

    def scene(self, s: pyspiel.State, viewer: int | None) -> dict:
        """Fallback view: the viewer's own observation as monospaced text.

        A spectator (``viewer`` is ``None``) sees the engine's full state string.
        """
        if viewer is None or self.is_terminal(s):
            text = str(s)
        else:
            text = self.observation(s, viewer)
        return scene.scene([scene.text(text, mono=True)], status=self.status(s, viewer))

    # ======================================================================= #
    # Bots
    # ======================================================================= #
    def mcts(self, simulations: int, name: str = "mcts", **kwargs: Any) -> MCTSPolicy:
        """An MCTS policy for this game, to return from a bot's policy method."""
        return MCTSPolicy(simulations, name=name, **kwargs)


# --------------------------------------------------------------------------- #
# Gymnasium
# --------------------------------------------------------------------------- #
@dataclass
class GymState:
    """A running episode.

    ``env`` is ``None`` until the reset seed (the opening chance outcome) is
    known. ``actions`` is the history and makes the state hashable by value.
    """

    env: Any = None
    seed: int | None = None
    obs: Any = None
    actions: list[int] = field(default_factory=list)
    total: float = 0.0
    last_reward: float = 0.0
    terminated: bool = False
    truncated: bool = False


class GymGame(Game):
    """Base class for single-agent Gymnasium environments with discrete actions.

    One player, no opponent. The return is the cumulative reward. See the
    module docstring for how a replayable episode is built from a seed.

    A concrete game sets :attr:`env_id` (and usually ``action_names``) and
    overrides :meth:`scene`.
    """

    family_id = "gymnasium"
    family_name = "Gymnasium environments"
    family_blurb = ("Control tasks from Farama's Gymnasium: one player, no opponent, a "
                    "reward after every step. This is where reinforcement learning "
                    "starts.")

    num_players = 1
    stochastic = True

    #: Registered Gymnasium id, e.g. ``"CartPole-v1"``.
    env_id: ClassVar[str] = ""
    #: Keyword arguments for ``gymnasium.make``.
    make_kwargs: ClassVar[dict[str, Any]] = {}
    #: One label per discrete action (empty: "action 0", "action 1", ...).
    action_names: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        env = self.make_env()
        space = env.action_space
        if type(space).__name__ != "Discrete":
            raise ValueError(f"{self.env_id}: GymGame needs a Discrete action space, got {space}")
        #: Number of discrete actions.
        self.n_actions: int = int(space.n)
        env.close()

    def make_env(self) -> Any:
        import gymnasium
        return gymnasium.make(self.env_id, disable_env_checker=True, **self.make_kwargs)

    # ======================================================================= #
    # Rules
    # ======================================================================= #
    def initial_state(self) -> GymState:
        return GymState()

    def copy_state(self, s: GymState) -> GymState:
        return GymState(
            env=copy.deepcopy(s.env) if s.env is not None else None, seed=s.seed,
            obs=copy.copy(s.obs), actions=list(s.actions), total=s.total,
            last_reward=s.last_reward, terminated=s.terminated, truncated=s.truncated)

    def current_player(self, s: GymState) -> int:
        return CHANCE if s.env is None else 0

    def legal_actions(self, s: GymState) -> list[Action]:
        return list(range(self.n_actions))

    def chance_outcomes(self, s: GymState) -> list[tuple[Action, float]]:
        raise NotImplementedError("the reset seed cannot be enumerated")

    def sample_chance(self, s: GymState, rng: random.Random) -> Action:
        return rng.randrange(SEED_LIMIT)

    def move(self, s: GymState, a: Action) -> None:
        if s.env is None:
            s.env = self.make_env()
            s.seed = int(a)
            s.obs, _info = s.env.reset(seed=s.seed)
            return
        obs, reward, terminated, truncated, _info = s.env.step(int(a))
        s.obs = obs
        s.last_reward = float(reward)
        s.total += float(reward)
        s.terminated = bool(terminated)
        s.truncated = bool(truncated)
        s.actions.append(int(a))

    def is_terminal(self, s: GymState) -> bool:
        return s.terminated or s.truncated

    def returns(self, s: GymState) -> list[float]:
        return [s.total]

    def key(self, s: GymState) -> str:
        return f"{s.seed}:{','.join(map(str, s.actions))}"

    # ======================================================================= #
    # Numbers for lenses and scenes
    # ======================================================================= #
    def obs_vector(self, s: GymState) -> list[float]:
        """The latest observation as plain floats (empty before the reset)."""
        if s.obs is None:
            return []
        values = s.obs.tolist() if hasattr(s.obs, "tolist") else s.obs
        return [float(v) for v in values] if isinstance(values, list) else [float(values)]

    def observation(self, s: GymState, player: int) -> str:
        return " ".join(f"{v:+.3f}" for v in self.obs_vector(s))

    # ======================================================================= #
    # Presentation
    # ======================================================================= #
    def action_label(self, s: GymState, a: Action) -> str:
        if s.env is None:
            return f"seed {a}"
        i = int(a)
        return self.action_names[i] if i < len(self.action_names) else f"action {i}"

    def describe(self, s: GymState, a: Action, player: int) -> str:
        return f"chooses {self.action_label(s, a)}"

    def describe_chance(self, s: GymState, a: Action) -> str:
        return f"resets the environment (seed {a})"

    def status(self, s: GymState, viewer: int | None) -> str:
        if s.env is None:
            return "Starting..."
        if self.is_terminal(s):
            how = "time is up" if s.truncated and not s.terminated else "episode over"
            return f"{how.capitalize()}: reward {s.total:g} in {len(s.actions)} steps"
        return f"Step {len(s.actions)}: reward so far {s.total:g}"

    def scene(self, s: GymState, viewer: int | None) -> dict:
        """Fallback view: the observation as bars plus one button per action."""
        names = [f"obs[{i}]" for i in range(len(self.obs_vector(s)))]
        bars = scene.bars([scene.bar(n, v, min=-abs(v) - 1, max=abs(v) + 1)
                           for n, v in zip(names, self.obs_vector(s))])
        parts = [bars]
        if not self.is_terminal(s) and s.env is not None:
            parts.append(scene.buttons([(a, self.action_label(s, a))
                                        for a in self.legal_actions(s)]))
        return scene.scene(parts, status=self.status(s, viewer))


__all__ = ["GymGame", "GymState", "MCTSPolicy", "SpielGame"]
