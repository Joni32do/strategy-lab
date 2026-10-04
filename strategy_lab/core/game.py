"""The base class every game inherits from.

A game is a *class*; its state is any Python object (a small dataclass is
the norm). The class describes the rules as functions of a state, in the
shape of OpenSpiel's API:

=========================  ==================================================
``initial_state()``        the start position (deterministic, no RNG)
``current_player(s)``      seat index ``0..n-1``, or :data:`CHANCE`
``legal_actions(s)``       the actions of the player to move
``move(s, a)``             mutate ``s`` in place (``s`` is already a copy)
``chance_outcomes(s)``     ``[(action, probability), ...]`` at chance nodes
``is_terminal(s)``         game over?
``returns(s)``             one float per seat (or implement ``winner(s)``)
=========================  ==================================================

Everything else (labels, captions, scenes, symmetry, heuristics, rule cards,
bots) has a sensible default and is overridden only where a game needs it.

All randomness lives in **chance nodes**: dice rolls, shuffles and deals are
actions of a pseudo-player :data:`CHANCE`. A whole game is therefore
reproducible from its action log alone, which is what makes undo, replays
and "edit the rules, keep playing" work.

Actions are ``int`` or ``str`` so they survive a JSON round trip unchanged.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Hashable

Action = int | str

#: Pseudo-player id of chance nodes (same value as OpenSpiel's ``kChancePlayerId``).
CHANCE = -1
#: Player id reported once the game is over (OpenSpiel's ``kTerminalPlayerId``).
TERMINAL = -4


# --------------------------------------------------------------------------- #
# Metadata records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Param:
    """A tweakable variant parameter, e.g. the target score in Pig.

    The type of ``default`` decides how incoming values are coerced.
    """

    default: Any
    label: str = ""
    help: str = ""
    choices: tuple = ()
    min: float | None = None
    max: float | None = None

    def coerce(self, value: Any) -> Any:
        """Convert ``value`` (often a JSON string or number) to the param type."""
        if value is None:
            return self.default
        kind = type(self.default)
        if kind is bool:
            if isinstance(value, str):
                value = value.strip().lower() in ("1", "true", "yes", "on")
            value = bool(value)
        else:
            value = kind(value)
        if self.min is not None and value < self.min:
            raise ValueError(f"{self.label or 'value'} must be >= {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"{self.label or 'value'} must be <= {self.max}")
        if self.choices and value not in self.choices:
            raise ValueError(f"{value!r} is not one of {list(self.choices)}")
        return value

    def to_json(self, name: str) -> dict:
        return {
            "name": name, "default": self.default, "label": self.label or name,
            "help": self.help, "choices": list(self.choices),
            "min": self.min, "max": self.max, "type": type(self.default).__name__,
        }


@dataclass(frozen=True)
class Card:
    """A rule card: one readable piece of strategy.

    A *policy* is an ordered stack of cards, read top to bottom each turn:

    * ``pick`` cards are called as ``fn(game, state, candidates, player, rng)``
      and return one of ``candidates`` or ``None`` (no opinion).
    * ``avoid`` cards are called as ``fn(game, state, action, player)`` and
      return ``True`` to veto that action for the cards below. A veto never
      removes the last candidate.

    The first pick card with an opinion decides. Without one, a random
    remaining candidate is played. Cards are declared with the :func:`pick`
    and :func:`avoid` decorators on game methods.
    """

    id: str
    name: str
    desc: str
    kind: str
    icon: str = ""
    fn: Callable | None = field(default=None, compare=False, repr=False)

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "desc": self.desc,
                "kind": self.kind, "icon": self.icon}


def pick(id: str, name: str, desc: str, icon: str = "") -> Callable:
    """Decorator: turn a game method into a PICK rule card.

    The method signature is ``(self, state, candidates, player, rng)``.
    Cards are inherited: a card defined on a family base class is available
    to every game of that family.
    """
    def deco(fn):
        fn._card = Card(id, name, desc, "pick", icon, fn)
        return fn
    return deco


def avoid(id: str, name: str, desc: str, icon: str = "") -> Callable:
    """Decorator: turn a game method into an AVOID rule card.

    The method signature is ``(self, state, action, player) -> bool``.
    """
    def deco(fn):
        fn._card = Card(id, name, desc, "avoid", icon, fn)
        return fn
    return deco


@dataclass(frozen=True)
class Bot:
    """An opponent persona.

    A bot plays either a stack of rule cards (``cards``, ids in order) or a
    custom policy: ``policy`` names a method of the game that returns a
    :class:`~strategy_lab.core.policy.Policy`. An empty bot plays randomly.
    """

    id: str
    name: str
    desc: str = ""
    stars: int = 1
    cards: tuple[str, ...] = ()
    policy: str = ""
    icon: str = "bot"

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "desc": self.desc,
                "stars": self.stars, "cards": list(self.cards), "icon": self.icon,
                "custom": bool(self.policy)}


@dataclass(frozen=True)
class Rulebook:
    """How to play, as short numbered steps.

    ``steps`` and ``extra`` hold ``(title, text)`` pairs. ``source`` links
    the official rules the implementation follows, if any.
    """

    summary: str
    steps: tuple[tuple[str, str], ...] = ()
    extra: tuple[tuple[str, str], ...] = ()
    source: str = ""

    def to_json(self) -> dict:
        return {
            "summary": self.summary,
            "steps": [{"title": t, "text": x} for t, x in self.steps],
            "extra": [{"title": t, "text": x} for t, x in self.extra],
            "source": self.source,
        }


@dataclass(frozen=True)
class Model:
    """One way to describe the game as a Markov decision process.

    Choosing the state space is a design decision: ``markov`` is ``True``,
    ``False`` or ``"approx"`` and says whether the state alone predicts the
    future, or whether some history still leaks in.
    """

    id: str
    name: str
    markov: bool | str
    state: str
    actions: str
    reward: str
    size: str = ""
    transition: str = ""
    note: str = ""

    def to_json(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class Challenge:
    """A goal that earns stars in the gallery.

    ``kind`` is one of:

    * ``finish``: play one game to the end.
    * ``win`` / ``draw``: reach that outcome (against ``bot`` if given).
    * ``score``: end with your return ``>= value``.
    * ``lens``: open the lens ``lens`` during a game.
    * ``sim``: a card stack simulated against ``bot`` reaches ``metric``
      (``"winrate"`` ``>= value``, or ``"no_loss"`` over 100 games).
    """

    id: str
    title: str
    kind: str
    stars: int = 1
    bot: str = ""
    value: float = 0.0
    lens: str = ""
    metric: str = "winrate"

    def to_json(self) -> dict:
        return dict(self.__dict__)


RANDOM_BOT = Bot("random", "Randy Rookie", "Plays a random legal move.", 1, icon="dice")


# --------------------------------------------------------------------------- #
# The base class
# --------------------------------------------------------------------------- #
class Game:
    """Base class of all games. Subclass it (or a family base class)."""

    # ---- catalog metadata (override as class attributes) ----------------- #
    #: Unique slug. Classes without their own ``id`` are abstract.
    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    #: Icon name from the frontend icon set (see ``web/js/icons.js``).
    icon: ClassVar[str] = "puzzle"
    tagline: ClassVar[str] = ""
    #: Chapter id of the learning path (see :mod:`strategy_lab.learn.curriculum`).
    chapter: ClassVar[str] = "workbench"
    #: Position inside the chapter; the unlock path follows it.
    order: ClassVar[int] = 100
    #: Concept ids (cheatsheet cards) this game teaches.
    concepts: ClassVar[tuple[str, ...]] = ()
    rulebook: ClassVar[Rulebook | None] = None
    models: ClassVar[tuple[Model, ...]] = ()
    bots: ClassVar[tuple[Bot, ...]] = (RANDOM_BOT,)
    challenges: ClassVar[tuple[Challenge, ...]] = (
        Challenge("finish", "Play a game to the end", "finish"),
    )
    params: ClassVar[dict[str, Param]] = {}
    num_players: ClassVar[int] = 2
    #: Short seat names, e.g. ``("X", "O")``. Empty: "Player 1", "Player 2"...
    seat_names: ClassVar[tuple[str, ...]] = ()
    #: Hard cap on log length; a game that runs longer ends by timeout.
    max_steps: ClassVar[int] = 5000
    #: Tests only: cap playouts in the conformance suite (slow engines).
    conformance_steps: ClassVar[int | None] = None
    #: Drafts live in the Workbench and are always unlocked.
    draft: ClassVar[bool] = False
    perfect_information: ClassVar[bool] = True
    #: The game has chance nodes (dice, shuffles). The odds lens needs it.
    stochastic: ClassVar[bool] = False
    #: Players choose at the same time (modelled as hidden sequential moves).
    simultaneous: ClassVar[bool] = False
    #: False: the page starts with bots in every seat (watch and tune).
    playable_by_human: ClassVar[bool] = True
    #: Card ids inherited from a base class that this game drops.
    exclude_cards: ClassVar[frozenset[str]] = frozenset()

    # ---- family metadata (set on family base classes) --------------------- #
    family_id: ClassVar[str] = ""
    family_name: ClassVar[str] = ""
    family_blurb: ClassVar[str] = ""

    def __init__(self, **params: Any) -> None:
        spec = self.param_spec()
        unknown = set(params) - set(spec)
        if unknown:
            raise ValueError(f"{self.id}: unknown parameter(s) {sorted(unknown)}")
        #: Resolved parameter values (defaults merged with overrides).
        self.p: dict[str, Any] = {k: spec[k].coerce(params.get(k)) for k in spec}

    # ======================================================================= #
    # Rules: override these
    # ======================================================================= #
    def initial_state(self) -> Any:
        """Return the start state. Randomness belongs in chance nodes."""
        raise NotImplementedError

    def current_player(self, s: Any) -> int:
        """Seat index of the player to move, or :data:`CHANCE`."""
        raise NotImplementedError

    def legal_actions(self, s: Any) -> list[Action]:
        """Actions of the player to move (never called at chance nodes)."""
        raise NotImplementedError

    def move(self, s: Any, a: Action) -> None:
        """Apply action ``a`` to ``s`` in place. ``s`` is a private copy."""
        raise NotImplementedError

    def is_terminal(self, s: Any) -> bool:
        raise NotImplementedError

    def winner(self, s: Any) -> int | None:
        """Winning seat or ``None`` (draw / undecided).

        Only used by the default :meth:`returns`; games with scores override
        :meth:`returns` instead.
        """
        raise NotImplementedError

    def returns(self, s: Any) -> list[float]:
        """Return per seat. Default: +1 for the winner, -1 for the others."""
        w = self.winner(s)
        if w is None:
            return [0.0] * self.num_players
        return [1.0 if seat == w else -1.0 for seat in range(self.num_players)]

    def chance_outcomes(self, s: Any) -> list[tuple[Action, float]]:
        """``[(outcome, probability), ...]`` at a chance node.

        Games whose chance events cannot be enumerated (a full shuffle)
        override :meth:`sample_chance` instead and may leave this raising.
        """
        raise NotImplementedError

    # ======================================================================= #
    # Derived rules: rarely overridden
    # ======================================================================= #
    def apply_action(self, s: Any, a: Action) -> Any:
        """Pure transition: copy ``s``, apply ``a``, return the copy."""
        ns = self.copy_state(s)
        self.move(ns, a)
        return ns

    def copy_state(self, s: Any) -> Any:
        """Deep copy by default; override for speed if a game needs it."""
        return copy.deepcopy(s)

    def is_chance(self, s: Any) -> bool:
        return not self.is_terminal(s) and self.current_player(s) == CHANCE

    def sample_chance(self, s: Any, rng) -> Action:
        """Draw one chance outcome with ``rng`` (a :class:`random.Random`)."""
        outcomes = self.chance_outcomes(s)
        r = rng.random()
        acc = 0.0
        for a, p in outcomes:
            acc += p
            if r < acc:
                return a
        return outcomes[-1][0]

    def chance_info(self, s: Any, a: Action) -> dict | None:
        """Probability facts about chance outcome ``a`` (for the odds lens)."""
        try:
            outcomes = self.chance_outcomes(s)
        except NotImplementedError:
            return None
        probs = [p for _, p in outcomes if p > 0]
        prob = next((p for o, p in outcomes if o == a), 0.0)
        entropy = -sum(p * math.log2(p) for p in probs)
        return {
            "prob": prob, "outcomes": len(probs), "entropy": entropy,
            "surprise": -math.log2(prob) if prob > 0 else None,
            "distribution": [{"a": o, "p": p, "label": self.action_label(s, o)}
                             for o, p in outcomes] if len(outcomes) <= 64 else None,
        }

    def key(self, s: Any) -> Hashable:
        """A hashable id of the position (used by solvers and RL tables)."""
        return repr(s)

    def canonical_key(self, s: Any) -> Hashable:
        """Like :meth:`key`, but equal for symmetric positions."""
        return self.key(s)

    def action_classes(self, s: Any, actions: list[Action]) -> list[list[Action]]:
        """Group ``actions`` into symmetry-equivalent classes.

        Default: no symmetry, every action is its own class.
        """
        return [[a] for a in actions]

    def observation(self, s: Any, player: int) -> str:
        """What ``player`` can see. Imperfect-information games override."""
        return str(self.key(s))

    def heuristic(self, s: Any, player: int) -> float | None:
        """Optional position estimate in ``[-1, 1]`` for depth-limited search."""
        return None

    def timeout_returns(self, s: Any) -> list[float]:
        """Returns when a game hits :attr:`max_steps`. Default: a draw."""
        return [0.0] * self.num_players

    def outcome(self, returns: list[float], player: int) -> str:
        """``"win"``, ``"draw"`` or ``"loss"`` for ``player`` given final returns."""
        best = max(returns)
        if returns[player] < best:
            return "loss"
        tops = sum(1 for r in returns if r == best)
        return "win" if tops == 1 else "draw"

    # ======================================================================= #
    # Presentation
    # ======================================================================= #
    def seat_label(self, seat: int) -> str:
        if seat < len(self.seat_names):
            return self.seat_names[seat]
        return f"Player {seat + 1}"

    def action_label(self, s: Any, a: Action) -> str:
        """Short button label for an action."""
        return str(a)

    def describe(self, s: Any, a: Action, player: int) -> str:
        """Log caption for ``player`` playing ``a`` in ``s`` (without the actor)."""
        return f"plays {self.action_label(s, a)}"

    def describe_chance(self, s: Any, a: Action) -> str:
        return f"chance: {self.action_label(s, a)}"

    def privacy(self, s: Any, a: Action, player: int) -> tuple[int, ...] | None:
        """Seats allowed to see this step in the move log; ``None`` = everyone.

        Hidden-information games return e.g. ``(seat,)`` for a card dealt to
        ``seat``. Other viewers see :meth:`describe_hidden` instead. (The
        browser holds the full log for replay, so this hides information in
        the interface, not cryptographically.)
        """
        return None

    def describe_hidden(self, s: Any, a: Action, player: int) -> str:
        """Log caption shown to viewers who may not see the step."""
        return "deals" if player == CHANCE else "makes a hidden move"

    def status(self, s: Any, viewer: int | None) -> str:
        """One-line headline above the board. Default is derived from the turn."""
        return ""

    def insight(self, stats: dict) -> str | None:
        """A takeaway for the results of a simulated match, or ``None``.

        ``stats`` is :meth:`~strategy_lab.core.match.MatchResult.to_json`;
        index 0 is the player's card stack, index 1 the opponent bot,
        ``stats["bot"]`` holds the opponent's bot id and ``stats["cards"]``
        the card ids of the player's stack.
        """
        return None

    def scene(self, s: Any, viewer: int | None) -> dict:
        """The view model for the frontend (see :mod:`strategy_lab.core.scene`).

        ``viewer`` is the seat the human sits in (hide what they cannot see),
        or ``None`` when spectating.
        """
        from strategy_lab.core import scene
        return scene.scene([scene.text(str(s), mono=True)])

    # ======================================================================= #
    # Strategy: cards and bots
    # ======================================================================= #
    @classmethod
    def cards(cls) -> list[Card]:
        """All rule cards, inherited ones first, minus :attr:`exclude_cards`."""
        found: dict[str, Card] = {}
        for klass in reversed(cls.__mro__):
            for attr in vars(klass).values():
                card = getattr(attr, "_card", None)
                if card is not None:
                    found[card.id] = card
        return [c for cid, c in found.items() if cid not in cls.exclude_cards]

    @classmethod
    def card(cls, card_id: str) -> Card:
        for c in cls.cards():
            if c.id == card_id:
                return c
        raise KeyError(f"{cls.id}: no card {card_id!r}")

    def bot(self, bot_id: str) -> Bot:
        for b in self.bots:
            if b.id == bot_id:
                return b
        if bot_id == RANDOM_BOT.id:
            return RANDOM_BOT
        raise KeyError(f"{self.id}: no bot {bot_id!r}")

    def make_policy(self, bot_id: str = "", cards: list[str] | None = None):
        """Policy for a bot id, or for an explicit card stack."""
        from strategy_lab.core.policy import RulePolicy
        if cards is not None:
            return RulePolicy([self.card(c) for c in cards], name="your stack")
        bot = self.bot(bot_id or RANDOM_BOT.id)
        if bot.policy:
            return getattr(self, bot.policy)()
        return RulePolicy([self.card(c) for c in bot.cards], name=bot.name)

    # ======================================================================= #
    # Catalog
    # ======================================================================= #
    @classmethod
    def param_spec(cls) -> dict[str, Param]:
        """Parameters merged along the class hierarchy (subclass wins).

        A subclass removes an inherited parameter by mapping it to ``None``.
        """
        spec: dict[str, Param] = {}
        for klass in reversed(cls.__mro__):
            for name, prm in (vars(klass).get("params") or {}).items():
                if prm is None:
                    spec.pop(name, None)
                else:
                    spec[name] = prm
        return spec

    @classmethod
    def lineage(cls) -> list[str]:
        """Class names from :class:`Game` down to this class."""
        chain = [k for k in reversed(cls.__mro__) if issubclass(k, Game)]
        return [k.__name__ for k in chain]

    @classmethod
    def family(cls) -> dict:
        """The nearest family base class: ``{"id", "name", "blurb", "base"}``."""
        for klass in cls.__mro__:
            if "family_id" in vars(klass) and klass.family_id:
                return {"id": klass.family_id, "name": klass.family_name,
                        "blurb": klass.family_blurb, "base": klass.__name__}
        return {"id": "standalone", "name": "Standalone", "blurb": "", "base": "Game"}

    @classmethod
    def is_concrete(cls) -> bool:
        return bool(vars(cls).get("id"))

    @classmethod
    def meta(cls) -> dict:
        """Compact catalog entry (gallery tile)."""
        return {
            "id": cls.id, "name": cls.name, "icon": cls.icon, "tagline": cls.tagline,
            "chapter": cls.chapter, "order": cls.order, "concepts": list(cls.concepts),
            "family": cls.family(), "lineage": cls.lineage(),
            "players": cls.num_players, "draft": cls.draft,
        }

    def detail(self) -> dict:
        """Full description for the game page."""
        d = self.meta()
        d.update({
            "rulebook": self.rulebook.to_json() if self.rulebook else None,
            "params": [p.to_json(n) for n, p in self.param_spec().items()],
            "values": dict(self.p),
            "bots": [b.to_json() for b in self.bots],
            "cards": [c.to_json() for c in self.cards()],
            "challenges": [c.to_json() for c in self.challenges],
            "models": [m.to_json() for m in self.models],
            "seats": [self.seat_label(i) for i in range(self.num_players)],
            "players": self.num_players,
            "perfectInformation": self.perfect_information,
            "stochastic": self.stochastic,
            "simultaneous": self.simultaneous,
            "playableByHuman": self.playable_by_human,
        })
        return d
