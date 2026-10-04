"""Dice families: games whose chance comes from rolling dice.

Two base classes live here.

:class:`DiceGame`
    Everything about rolling. It splits :meth:`~strategy_lab.core.game.Game.move`
    into :meth:`DiceGame.resolve_chance` (a die lands) and :meth:`DiceGame.play`
    (a player decides), so a concrete game never branches on "is this a chance
    node?" itself. It also keeps the ``fresh`` flag that makes the browser
    animate a new roll, builds ``dice`` scene parts, enumerates the exact
    probabilities of one die or of a pair of dice, and copies states quickly.

:class:`RollAndMoveGame`
    Tokens travel along a track. It adds one movement helper that covers the
    three ways a track ends (stop, bounce, loop) and reports every square the
    token passed, plus the position-based timeout rule shared by the family.

====================  =====  =====================================================
game                  base   what is special
====================  =====  =====================================================
Pig                   dice   one die, push your luck
Qwixx                 dice   six dice, a sheet instead of a board
Snakes & Ladders      move   two dice, keep one; bounce off the last square
Mensch aergere dich   move   one die, four tokens, captures
Monopoly              move   two dice, a ring of 40 spaces, decisions after landing
The Game of Life      move   a spinner, a life road with forks
====================  =====  =====================================================

Chance conventions
------------------
All randomness lives in chance nodes (``to_move == CHANCE``). One die is an
``int`` outcome (``1..sides``). A pair of dice is a ``"a-b"`` string, so a
game that only cares about the sum and about doubles needs one chance node
per roll and not two. The unordered pair has 21 outcomes with exact
probabilities (1/36 for a double, 2/36 for the rest). Dice games with a
chance node that is not a die (a card draw, a spinner) simply return their
own ``chance_outcomes``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, NamedTuple, Sequence

from strategy_lab.core import CHANCE, Game, scene
from strategy_lab.core.game import Action

_LEAF = (int, float, str, bool, type(None), tuple)


def clone(value: Any) -> Any:
    """Copy a state built from dataclasses, lists, dicts, sets and plain leaves.

    A drop-in for :func:`copy.deepcopy` that is several times faster because
    it does not track object identity. States must therefore be trees (no
    shared sublists) and tuples must hold immutable values only.
    """
    kind = type(value)
    if kind in _LEAF:
        return value
    if kind is list:
        return [x if type(x) in _LEAF else clone(x) for x in value]
    if kind is dict:
        return {k: (x if type(x) in _LEAF else clone(x)) for k, x in value.items()}
    if kind is set:
        return set(value)
    new = object.__new__(kind)  # a dataclass instance
    new.__dict__ = {k: (x if type(x) in _LEAF else clone(x)) for k, x in value.__dict__.items()}
    return new


@dataclass
class DiceState:
    """Fields every dice game keeps; concrete states extend it.

    Add your own fields as keyword-only ones::

        @dataclass(kw_only=True)
        class PigState(DiceState):
            scores: list[int] = field(default_factory=lambda: [0, 0])
    """

    #: Seat that must act now, or :data:`~strategy_lab.core.game.CHANCE`.
    to_move: int = 0
    #: Seat whose turn it is. During a chance node ``to_move`` is CHANCE but
    #: ``turn`` still says whose roll is being resolved.
    turn: int = 0
    #: True right after a roll: the scene asks the browser to animate the dice.
    fresh: bool = False


def _article(n: int) -> str:
    return "an" if n in (8, 11, 18) else "a"


class DiceGame(Game):
    """Base class of all dice games. See the module docstring.

    Concrete games implement :meth:`resolve_chance` and :meth:`play` instead
    of :meth:`~strategy_lab.core.game.Game.move`, and :meth:`move_label`
    instead of :meth:`~strategy_lab.core.game.Game.action_label`. Their state
    extends :class:`DiceState`.
    """

    family_id = "dice"
    family_name = "Dice games"
    family_blurb = ("Luck you can count. Dice have no memory, so every roll has exact "
                    "odds, and a good policy is the one that uses them best.")

    stochastic = True

    # ----------------------------------------------------------------- rules glue
    def current_player(self, s: DiceState) -> int:
        return s.to_move

    def move(self, s: DiceState, a: Action) -> None:
        """Route the action: chance outcomes to :meth:`resolve_chance`, rest to :meth:`play`."""
        if s.to_move == CHANCE:
            s.fresh = True
            self.resolve_chance(s, a)
        else:
            s.fresh = False
            self.play(s, a)

    def resolve_chance(self, s: Any, outcome: Action) -> None:
        """A die (or card, or spinner) landed on ``outcome``. Mutate ``s``."""
        raise NotImplementedError

    def play(self, s: Any, action: Action) -> None:
        """The player to move chose ``action``. Mutate ``s``."""
        raise NotImplementedError

    def copy_state(self, s: Any) -> Any:
        return clone(s)

    # ------------------------------------------------------------ exact outcomes
    @staticmethod
    def die_outcomes(sides: int = 6) -> list[tuple[int, float]]:
        """One fair die: ``[(1, 1/6), ..., (6, 1/6)]``."""
        return [(face, 1.0 / sides) for face in range(1, sides + 1)]

    @staticmethod
    def pair_outcomes(sides: int = 6, ordered: bool = False) -> list[tuple[str, float]]:
        """Two fair dice as ``"a-b"`` strings with exact probabilities.

        Unordered (default): ``a <= b``, 21 outcomes, a double has probability
        ``1/36`` and every other pair ``2/36``. Ordered: all 36 pairs at ``1/36``.
        """
        total = float(sides * sides)
        out: list[tuple[str, float]] = []
        for a in range(1, sides + 1):
            for b in range(1 if ordered else a, sides + 1):
                weight = 1.0 if (ordered or a == b) else 2.0
                out.append((f"{a}-{b}", weight / total))
        return out

    @staticmethod
    def parse_pair(outcome: Action) -> tuple[int, int]:
        """``"3-5"`` -> ``(3, 5)``."""
        a, b = str(outcome).split("-")
        return int(a), int(b)

    @staticmethod
    def is_double(outcome: Action) -> bool:
        a, b = DiceGame.parse_pair(outcome)
        return a == b

    # ---------------------------------------------------------------- presentation
    def roll_text(self, outcome: Action) -> str:
        """Words for an outcome: ``a 4``, ``3 and 5``, ``double 6``."""
        if isinstance(outcome, int):
            return f"{_article(outcome)} {outcome}"
        a, b = self.parse_pair(outcome)
        return f"double {a}" if a == b else f"{a} and {b}"

    def describe_chance(self, s: Any, a: Action) -> str:
        return f"rolls {self.roll_text(a)}"

    def outcome_label(self, s: Any, a: Action) -> str:
        """Short label of a chance outcome (the odds lens lists them)."""
        if isinstance(a, str) and "-" in a:
            x, y = self.parse_pair(a)
            return f"{x} + {y}"
        return str(a)

    def move_label(self, s: Any, a: Action) -> str:
        """Button label of a decision. Override in concrete games."""
        return str(a)

    def action_label(self, s: Any, a: Action) -> str:
        if self.is_chance(s):
            return self.outcome_label(s, a)
        return self.move_label(s, a)

    # ---------------------------------------------------------------- scene helpers
    def dice_part(self, values: Sequence[int], *, tones: Sequence[str] | str = "white",
                  actions: Sequence[Action | None] | None = None,
                  held: Sequence[bool] | None = None, sides: int = 6,
                  fresh: bool = False, caption: str = "") -> dict:
        """A ``dice`` scene part with per-die tones, actions and held flags.

        Args:
            values: the face value of each die.
            tones: one tone for all dice or one per die (``white``, ``red``...).
            actions: per die, the action clicking it plays (``None``: inert).
            held: per die, True draws it as set aside.
            fresh: play the roll animation (pass ``state.fresh``).
        """
        out = []
        for i, v in enumerate(values):
            tone = tones if isinstance(tones, str) else tones[i]
            out.append(scene.die(v, sides=sides, tone=tone,
                                 held=bool(held[i]) if held else False,
                                 action=actions[i] if actions else None))
        return scene.dice(out, caption=caption, fresh=fresh)

    def seat_name(self, seat: int, viewer: int | None) -> str:
        """``"You"`` for the viewer's own seat, else the seat label."""
        return "You" if seat == viewer else self.seat_label(seat)

    def scoreboard(self, s: DiceState, viewer: int | None, *,
                   score: Callable[[int], Any] | None = None,
                   sub: Callable[[int], str] | None = None) -> list[dict]:
        """One scoreboard row per seat; the seat whose turn it is lights up.

        Args:
            score: ``seat -> value`` for the big number (money, a square).
            sub: ``seat -> text`` for the second line.
        """
        live = not self.is_terminal(s)
        return [scene.player(self.seat_name(seat, viewer),
                             score=score(seat) if score else None,
                             sub=sub(seat) if sub else "",
                             active=live and seat == s.turn, owner=seat)
                for seat in range(self.num_players)]

    # --------------------------------------------------------------------- results
    def returns_from_scores(self, scores: Sequence[float]) -> list[float]:
        """Win/draw/loss returns from final scores.

        A unique top score gets ``+1`` and everyone else ``-1``. If several
        seats share the top score they get ``0`` (a draw) and the rest ``-1``.
        """
        best = max(scores)
        tops = [i for i, v in enumerate(scores) if v == best]
        if len(tops) == 1:
            return [1.0 if i == tops[0] else -1.0 for i in range(len(scores))]
        return [0.0 if i in tops else -1.0 for i in range(len(scores))]

    @staticmethod
    def squash(x: float, scale: float) -> float:
        """Map a lead in points to ``(-1, 1)`` (for :meth:`heuristic`)."""
        return math.tanh(x / scale)


class Advance(NamedTuple):
    """Result of :meth:`RollAndMoveGame.advance`."""

    #: The square the token ends on.
    dest: int
    #: Every square the token entered, in order, the destination last.
    path: tuple[int, ...]
    #: True if the token ran past the last square and turned back (``bounce``).
    bounced: bool = False


class RollAndMoveGame(DiceGame):
    """Base class of games where tokens travel along a track.

    The shared parts are the movement rule (:meth:`advance`), the token
    marks of a ``track`` scene (:meth:`token_marks`) and the way a game that
    runs out of steps is decided: whoever stands furthest ahead wins
    (:meth:`standing`).
    """

    family_id = "roll-and-move"
    family_name = "Roll and move"
    family_blurb = ("Roll, move, see what the square does. Most choices hide in what you "
                    "do after landing: which die, which token, buy or not.")

    # -------------------------------------------------------------------- movement
    @staticmethod
    def advance(pos: int, steps: int, last: int, mode: str = "stop") -> Advance:
        """Move ``steps`` squares from ``pos`` on a track of squares ``0..last``.

        ``mode`` says what happens at the end of the track:

        ``"stop"``
            the token halts on the last square (a road that ends).
        ``"bounce"``
            the remaining steps count backwards from the last square, as in
            Snakes and Ladders (``98 + 4`` ends on ``98``, not on ``102``).
        ``"loop"``
            the track is a ring of ``last + 1`` squares (Monopoly). Check
            ``0 in result.path`` to see whether the token passed the start.

        Every square the token entered is in :attr:`Advance.path`, so a game
        can apply "passed square X" events (a salary, a paycheck) in order.
        """
        if mode == "loop":
            ring = last + 1
            path = tuple((pos + i) % ring for i in range(1, steps + 1))
            return Advance(path[-1] if path else pos, path)
        if mode == "stop":
            path = tuple(range(pos + 1, min(pos + steps, last) + 1))
            return Advance(path[-1] if path else pos, path)
        if mode == "bounce":
            at, direction, path = pos, 1, []
            for _ in range(steps):
                if at == last:
                    direction = -1
                at += direction
                path.append(at)
            return Advance(at, tuple(path), bounced=pos + steps > last)
        raise ValueError(f"unknown track mode {mode!r}")

    # ------------------------------------------------------------------ scene helper
    def token_marks(self, positions: Sequence[int | None]) -> list[dict]:
        """``track`` tokens, one per seat; ``None`` positions (off the board) are skipped."""
        return [scene.token(seat, at) for seat, at in enumerate(positions) if at is not None]

    # --------------------------------------------------------------------- timeouts
    def standing(self, s: Any, seat: int) -> float:
        """How far ahead ``seat`` is (bigger is better). Decides a timeout."""
        return 0.0

    def timeout_returns(self, s: Any) -> list[float]:
        return self.returns_from_scores([self.standing(s, i) for i in range(self.num_players)])
