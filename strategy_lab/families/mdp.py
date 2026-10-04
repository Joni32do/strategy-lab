"""Single-agent worlds: games that are Markov decision processes.

One player, no opponent. Each step the agent picks an action, the world
answers with a new state and a reward, and the *return* is the sum of the
rewards. That is the whole setting of reinforcement learning.

* :class:`SinglePlayerGame`: the base class. ``returns`` is the reward
  collected so far. A game may expose its *model* for planning:
  :meth:`~SinglePlayerGame.states` and :meth:`~SinglePlayerGame.transitions`.
  The default model is derived from the rules by enumerating chance nodes.
* :class:`GridWorld`: a map of tiles (start, goal, hole, cliff, wall, free),
  four moves and optional slipping. FrozenLake and Cliff Walking are two
  maps with other rewards. Its *tabular model* ``model[cell][move]`` has the
  same shape as Gymnasium's ``env.P``.

The RL toolkit
--------------
Small functions named after the ideas, shared by the bots here and by the
``rl`` lens:

========================  =====================================================
:func:`value_iteration`   dynamic programming with the Bellman optimality backup
:func:`greedy_actions`    the best actions of a row of Q-values (ties kept)
:func:`greedy_probs`      uniform over the greedy actions
:func:`epsilon_greedy_probs`  greedy with probability 1 - eps, random with eps
:func:`softmax_probs`     Boltzmann exploration: better actions are likelier
:func:`entropy_bits`      how random a policy is, in bits
========================  =====================================================

Rule cards of a grid world: ``goal`` (walk toward the goal), ``plan`` (follow
the value-iteration plan), and the vetoes ``safe`` and ``bump``.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Any, ClassVar, Hashable, Sequence

from strategy_lab.core import CHANCE, Game, Param, avoid, pick, scene
from strategy_lab.core.game import Action

#: The four moves, clockwise from "up". The neighbors in this cycle are the
#: perpendicular moves: a slip from "up" goes "left" or "right".
DIRECTIONS = ("up", "right", "down", "left")
STEP = {"up": (-1, 0), "right": (0, 1), "down": (1, 0), "left": (0, -1)}

#: ``(probability, next cell, reward, episode over)``, like Gymnasium's ``env.P``.
Transition = tuple[float, int, float, bool]
Model = dict[int, dict[str, list[Transition]]]


def perpendicular(direction: str) -> tuple[str, str]:
    """The two moves at right angles to ``direction``."""
    i = DIRECTIONS.index(direction)
    return DIRECTIONS[(i - 1) % 4], DIRECTIONS[(i + 1) % 4]


# --------------------------------------------------------------------------- #
# The RL toolkit
# --------------------------------------------------------------------------- #
def entropy_bits(probs: Sequence[float]) -> float:
    """Shannon entropy ``-sum p log2 p`` in bits: 0 for a sure action, 2 for 4 equal ones."""
    return float(max(0.0, -sum(p * math.log2(p) for p in probs if p > 1e-12)))


def greedy_actions(values: dict[str, float] | Sequence[float], tol: float = 1e-9) -> list:
    """The keys (or indices) of the largest values. Ties within ``tol`` all count."""
    items = list(values.items()) if isinstance(values, dict) else list(enumerate(values))
    best = max(v for _, v in items)
    return [k for k, v in items if v >= best - tol]


def greedy_probs(values: Sequence[float]) -> list[float]:
    """Play uniformly among the best actions (the policy of a greedy learner)."""
    best = set(greedy_actions(values))
    return [1.0 / len(best) if i in best else 0.0 for i in range(len(values))]


def epsilon_greedy_probs(values: Sequence[float], epsilon: float) -> list[float]:
    """With probability ``epsilon`` explore uniformly, otherwise exploit the best action."""
    n = len(values)
    greedy = greedy_probs(values)
    return [epsilon / n + (1.0 - epsilon) * g for g in greedy]


def softmax_probs(values: Sequence[float], temperature: float) -> list[float]:
    """Boltzmann exploration: ``p_i ~ exp(v_i / temperature)``.

    A high temperature is close to random, a low one close to greedy.
    """
    top = max(values)
    weights = [math.exp((v - top) / max(temperature, 1e-6)) for v in values]
    total = sum(weights)
    return [w / total for w in weights]


@dataclass
class PlanResult:
    """Output of :func:`value_iteration`.

    Attributes:
        values: ``V(s)`` for every cell.
        q: ``Q(s, a)`` for every cell and move.
        sweeps: how many sweeps over all cells were needed.
        deltas: the largest change of any ``V(s)`` in each sweep.
    """

    values: dict[int, float]
    q: dict[int, dict[str, float]]
    sweeps: int
    deltas: list[float] = field(default_factory=list)

    def best_actions(self, cell: int) -> list[str]:
        """The greedy moves in ``cell`` (all of them if the Q-values tie)."""
        return greedy_actions(self.q[cell])


def value_iteration(model: Model, gamma: float = 0.99, theta: float = 1e-7,
                    max_sweeps: int = 1000) -> PlanResult:
    """Dynamic programming: repeat the Bellman optimality backup until values settle.

    ``Q(s, a) = sum_s' p(s' | s, a) [ r + gamma V(s') ]`` and ``V(s) = max_a Q(s, a)``,
    where ``V`` of an episode-ending next state is 0. Stops when no value moves
    by more than ``theta``.
    """
    values = {s: 0.0 for s in model}
    deltas: list[float] = []
    q: dict[int, dict[str, float]] = {}
    for sweep in range(1, max_sweeps + 1):
        delta = 0.0
        for s, actions in model.items():
            q[s] = {a: sum(p * (r + (0.0 if done else gamma * values[nxt]))
                           for p, nxt, r, done in outcomes)
                    for a, outcomes in actions.items()}
            best = max(q[s].values())
            delta = max(delta, abs(best - values[s]))
            values[s] = best
        deltas.append(delta)
        if delta < theta:
            return PlanResult(values, q, sweep, deltas)
    return PlanResult(values, q, max_sweeps, deltas)


_PLAN_CACHE: dict[Hashable, PlanResult] = {}


# --------------------------------------------------------------------------- #
# Single-player games
# --------------------------------------------------------------------------- #
class SinglePlayerGame(Game):
    """One seat against the world. States must carry a ``total`` (reward so far)."""

    family_id = "mdp"
    family_name = "Single-agent worlds"
    family_blurb = ("One player against the world: choose, collect a reward, repeat. "
                    "These are Markov decision processes, the setting of reinforcement "
                    "learning.")

    num_players = 1
    #: A finished game with ``return >= win_return`` counts as a win.
    win_return: ClassVar[float] = 0.0

    def returns(self, s: Any) -> list[float]:
        return [s.total]

    def timeout_returns(self, s: Any) -> list[float]:
        return [s.total]

    def outcome(self, returns: list[float], player: int) -> str:
        return "win" if returns[0] >= self.win_return else "loss"

    # ------------------------------------------------------------------ model
    def transitions(self, s: Any, a: Action) -> list[tuple[float, Any, float]]:
        """The world's answer to ``a`` in ``s``: ``[(probability, next state, reward)]``.

        Derived from the rules: apply ``a``, then follow every chance outcome
        until the agent has to decide again or the episode ends. The reward
        of a branch is the change of the running total.
        """
        out = []
        frontier = deque([(1.0, self.apply_action(s, a))])
        while frontier:
            p, ns = frontier.popleft()
            if not self.is_terminal(ns) and self.current_player(ns) == CHANCE:
                for outcome, q in self.chance_outcomes(ns):
                    frontier.append((p * q, self.apply_action(ns, outcome)))
            else:
                out.append((p, ns, ns.total - s.total))
        return out

    def states(self, limit: int = 100_000) -> list[Any]:
        """Every state the agent can decide in, found by exploring from the start.

        Only sensible when the reachable set is small. Raises ``RuntimeError``
        beyond ``limit`` states (a step counter or a running total makes the
        set grow quickly: grid worlds override this with a time-free list).
        """
        start = self.initial_state()
        while not self.is_terminal(start) and self.current_player(start) == CHANCE:
            start = self.apply_action(start, self.chance_outcomes(start)[0][0])
        seen = {self.key(start): start}
        frontier = deque([start])
        while frontier:
            s = frontier.popleft()
            if self.is_terminal(s):
                continue
            for a in self.legal_actions(s):
                for _, ns, _ in self.transitions(s, a):
                    k = self.key(ns)
                    if k not in seen:
                        if len(seen) >= limit:
                            raise RuntimeError(f"more than {limit} states")
                        seen[k] = ns
                        frontier.append(ns)
        return list(seen.values())


# --------------------------------------------------------------------------- #
# Grid worlds
# --------------------------------------------------------------------------- #
@dataclass
class GridState:
    """Where the agent is and what it has collected.

    Attributes:
        pos: cell index ``row * cols + col``.
        total: reward collected so far (the return).
        steps: moves made so far (compared with the step limit).
        pending: the intended move while the slip chance node is open, else "".
        done: the episode ended in the goal or a hole.
        last: the cell the agent came from (shown as the last move).
    """

    pos: int
    total: float = 0.0
    steps: int = 0
    pending: str = ""
    done: bool = False
    last: int | None = None


class GridWorld(SinglePlayerGame):
    """A map of tiles with four moves and optional slipping.

    Tile characters: ``S`` start, ``G`` goal, ``H`` hole, ``C`` cliff,
    ``#`` wall and ``.`` free. Entering a goal or a hole ends the episode.
    Entering a cliff costs its reward and puts the agent back on the start.
    A move into a wall or off the map leaves the agent where it is.

    A subclass sets :attr:`layout` (or :meth:`make_layout`), :attr:`rewards`
    and the metadata. The reward of a move is looked up by the tile entered.
    """

    family_id = "gridworld"
    family_name = "Grid worlds"
    family_blurb = ("A map, four moves, a reward for reaching the goal. Walk it by hand, "
                    "then watch value iteration and Q-learning solve it.")

    params = {
        "slippery": Param(False, "Slippery", "On a slippery map the move you choose only "
                                             "happens 1 time in 3. Otherwise you slide "
                                             "sideways."),
        "limit": Param(0, "Step limit", "The game stops after this many moves. 0 uses the "
                                        "default of the map.", min=0, max=1000),
    }

    layout: ClassVar[tuple[str, ...]] = ()
    #: Reward for entering a tile of this kind. Missing kinds pay 0.
    rewards: ClassVar[dict[str, float]] = {}
    #: Background tone of free tiles (see :mod:`strategy_lab.core.scene`).
    free_tone: ClassVar[str] = "ice"
    #: Chance of moving as intended on a slippery map; the rest is split sideways.
    success_rate: ClassVar[float] = 1.0 / 3.0
    default_limit: ClassVar[int] = 100

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.tiles: tuple[str, ...] = tuple(self.make_layout())
        self._check_layout()
        self.rows = len(self.tiles)
        self.cols = len(self.tiles[0])
        flat = "".join(self.tiles)
        self.start = flat.index("S")
        self.slippery = bool(self.p["slippery"])
        self.stochastic = self.slippery      # slipping is the only chance in a grid world
        self.step_limit = self.p["limit"] or self.default_steps()

    def default_steps(self) -> int:
        """Step limit used when the ``limit`` parameter is 0."""
        return self.default_limit

    def make_layout(self) -> Sequence[str]:
        """The map to play on. Override when a parameter chooses between maps."""
        return self.layout

    def _check_layout(self) -> None:
        widths = {len(row) for row in self.tiles}
        flat = "".join(self.tiles)
        if len(widths) != 1 or flat.count("S") != 1 or "G" not in flat:
            raise ValueError("a map needs equal row lengths, one S and at least one G")
        if set(flat) - set("SGHC#."):
            raise ValueError("map tiles are S G H C # and .")

    # ------------------------------------------------------------------ map
    def tile(self, cell: int) -> str:
        r, c = divmod(cell, self.cols)
        return self.tiles[r][c]

    def neighbor(self, cell: int, direction: str) -> int | None:
        """The cell next to ``cell`` in ``direction``, or ``None`` (edge or wall)."""
        r, c = divmod(cell, self.cols)
        dr, dc = STEP[direction]
        nr, nc = r + dr, c + dc
        if not (0 <= nr < self.rows and 0 <= nc < self.cols) or self.tiles[nr][nc] == "#":
            return None
        return nr * self.cols + nc

    def target_tile(self, cell: int, direction: str) -> str:
        """The tile a move would run into (the agent's own tile if it would bump)."""
        nxt = self.neighbor(cell, direction)
        return self.tile(cell if nxt is None else nxt)

    def entered(self, cell: int, direction: str) -> tuple[int, float, bool]:
        """One physical step: ``(new cell, reward, episode over)``.

        The single place where the map rules live: the game rules and the
        tabular model both call it, so they cannot disagree.
        """
        nxt = self.neighbor(cell, direction)
        tile = self.tile(cell if nxt is None else nxt)
        reward = self.rewards.get(tile, 0.0)
        if tile == "C":
            return self.start, reward, False
        return (cell if nxt is None else nxt), reward, tile in "GH"

    def slip_outcomes(self, action: str) -> list[tuple[str, float]]:
        """Where a move can really go: ``[(direction, probability)]``."""
        if not self.slippery:
            return [(action, 1.0)]
        left, right = perpendicular(action)
        side = (1.0 - self.success_rate) / 2.0
        return [(left, side), (action, self.success_rate), (right, side)]

    # ---------------------------------------------------------------- rules
    def initial_state(self) -> GridState:
        return GridState(pos=self.start)

    def copy_state(self, s: GridState) -> GridState:
        return replace(s)

    def current_player(self, s: GridState) -> int:
        return CHANCE if s.pending else 0

    def legal_actions(self, s: GridState) -> list[Action]:
        return list(DIRECTIONS)

    def chance_outcomes(self, s: GridState) -> list[tuple[Action, float]]:
        return self.slip_outcomes(s.pending)

    def move(self, s: GridState, a: Action) -> None:
        if s.pending:
            s.pending = ""
            self._walk(s, str(a))
        elif self.slippery:
            s.pending = str(a)
        else:
            self._walk(s, str(a))

    def _walk(self, s: GridState, direction: str) -> None:
        cell, reward, done = self.entered(s.pos, direction)
        s.last, s.pos = s.pos, cell
        s.total += reward
        s.steps += 1
        s.done = done

    def is_terminal(self, s: GridState) -> bool:
        return s.done or s.steps >= self.step_limit

    def key(self, s: GridState) -> tuple:
        return (s.pos, s.total, s.steps, s.pending, s.done)

    # ---------------------------------------------------------- planning model
    @cached_property
    def model(self) -> Model:
        """The tabular model ``model[cell][move] = [(p, next cell, reward, done), ...]``.

        Time-free: the step limit is not part of the planning state (Gymnasium
        keeps its time limit outside the environment in the same way).
        """
        table: Model = {}
        for cell in range(self.rows * self.cols):
            tile = self.tile(cell)
            if tile == "#":
                continue
            table[cell] = {}
            for move in DIRECTIONS:
                if tile in "GH":
                    table[cell][move] = [(1.0, cell, 0.0, True)]
                    continue
                merged: dict[tuple[int, float, bool], float] = {}
                for direction, p in self.slip_outcomes(move):
                    outcome = self.entered(cell, direction)
                    merged[outcome] = merged.get(outcome, 0.0) + p
                table[cell][move] = [(p, nxt, r, done) for (nxt, r, done), p in merged.items()]
        return table

    def states(self, limit: int = 100_000) -> list[GridState]:
        """One state per cell the agent can decide in (time-free, see :attr:`model`).

        Goals and holes end the episode and a cliff cell is never occupied.
        """
        return [GridState(pos=c) for c in self.model if self.tile(c) not in "GHC"]

    def transitions(self, s: GridState, a: Action) -> list[tuple[float, GridState, float]]:
        return [(p, GridState(nxt, s.total + r, s.steps + 1, "", done, s.pos), r)
                for p, nxt, r, done in self.model[s.pos][str(a)]]

    def optimal(self, gamma: float = 0.99) -> PlanResult:
        """Value iteration on this map, cached across games with the same map and rules."""
        key = (self.tiles, tuple(sorted(self.rewards.items())), self.slippery,
               self.success_rate, gamma)
        if key not in _PLAN_CACHE:
            if len(_PLAN_CACHE) > 64:
                _PLAN_CACHE.clear()
            _PLAN_CACHE[key] = value_iteration(self.model, gamma)
        return _PLAN_CACHE[key]

    @cached_property
    def goal_distance(self) -> dict[int, int]:
        """Walking distance to the nearest goal over tiles that are safe to step on."""
        goals = [c for c in self.model if self.tile(c) == "G"]
        dist = {g: 0 for g in goals}
        frontier = deque(goals)
        while frontier:
            cell = frontier.popleft()
            for d in DIRECTIONS:
                nxt = self.neighbor(cell, d)
                if nxt is not None and nxt not in dist and self.tile(nxt) not in "HC":
                    dist[nxt] = dist[cell] + 1
                    frontier.append(nxt)
        return dist

    # ------------------------------------------------------------- rule cards
    @pick("goal", "Head for the goal",
          "Take a step along the shortest route to the goal that avoids holes and cliffs.",
          "flag")
    def card_goal(self, s, candidates, player, rng):
        dist = self.goal_distance
        here = dist.get(s.pos)
        if here is None:
            return None
        closer = []
        for a in candidates:
            nxt, _, _ = self.entered(s.pos, a)
            if dist.get(nxt, here) < here and self.target_tile(s.pos, a) not in "HC":
                closer.append(a)
        return rng.choice(closer) if closer else None

    @pick("plan", "Follow the Bellman plan",
          "Use the values from value iteration: always take the move with the best "
          "expected return.", "brain")
    def card_plan(self, s, candidates, player, rng):
        best = [a for a in self.optimal().best_actions(s.pos) if a in candidates]
        return rng.choice(best) if best else None

    @avoid("safe", "Avoid danger",
           "Skip any move that could end in a hole or on a cliff, even by slipping.",
           "barrier")
    def card_safe(self, s, a, player):
        return any(self.target_tile(s.pos, d) in "HC" for d, _ in self.slip_outcomes(a))

    @avoid("bump", "Don't bump walls",
           "Skip moves that run into a wall or the edge and go nowhere.", "corner")
    def card_bump(self, s, a, player):
        return self.neighbor(s.pos, a) is None

    # ----------------------------------------------------------- presentation
    def action_label(self, s: GridState, a: Action) -> str:
        return str(a).capitalize()

    def describe(self, s: GridState, a: Action, player: int) -> str:
        return f"steps {a}" if not self.slippery else f"tries to go {a}"

    def describe_chance(self, s: GridState, a: Action) -> str:
        if a == s.pending:
            return f"moves {a} as intended"
        return f"slips: moves {a} instead of {s.pending}"

    def observation(self, s: GridState, player: int) -> str:
        r, c = divmod(s.pos, self.cols)
        return f"row {r}, column {c}"

    def status(self, s: GridState, viewer: int | None) -> str:
        if s.done:
            tile = self.tile(s.pos)
            if tile == "G":
                return f"You reached the goal. Return {s.total:g}"
            return f"You fell into a hole. Return {s.total:g}"
        if self.is_terminal(s):
            return f"Out of steps. Return {s.total:g}"
        if s.pending:
            return "The ground slips..."
        return f"Step {s.steps + 1} of {self.step_limit}: choose a direction"

    def _tile_cell(self, cell: int, s: GridState, action: str | None) -> dict:
        tile = self.tile(cell)
        tones = {"S": "start", "G": "goal", "H": "hole", "C": "cliff", "#": "wall",
                 ".": self.free_tone}
        reward = self.rewards.get(tile, 0.0)
        base = self.rewards.get(".", 0.0)
        badge = f"{reward:+g}" if tile in "GHC" and reward != base else ""
        icon = {"G": "flag", "C": "mountain"}.get(tile, "")
        pieces = [scene.piece(0, "agent")] if cell == s.pos else []
        return scene.cell(pieces=pieces, tone=tones[tile], action=action, badge=badge, icon=icon)

    def scene(self, s: GridState, viewer: int | None) -> dict:
        acting = not self.is_terminal(s) and not s.pending
        moves: dict[int, str] = {}
        if acting:
            for d in DIRECTIONS:
                nxt = self.neighbor(s.pos, d)
                if nxt is not None:
                    moves[nxt] = d
        cells = [self._tile_cell(c, s, moves.get(c)) for c in range(self.rows * self.cols)]
        board = scene.grid(self.rows, self.cols, cells, style="tiles",
                           caption="Slippery: the move you pick happens 1 time in 3."
                           if self.slippery else "")
        me = scene.player("You", score=f"{s.total:g}", sub=f"step {s.steps} of "
                          f"{self.step_limit}", active=acting, owner=0)
        return scene.scene([board], players=[me], status=self.status(s, viewer))
