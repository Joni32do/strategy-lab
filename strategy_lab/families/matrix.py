"""Matrix games: both players choose at once, one payoff table decides.

A *normal-form* game is a table. Row player and column player each pick one
action without seeing the other's pick, then both get the payoff in the cell
where the picks meet. :class:`MatrixGame` repeats such a game for ``rounds``
rounds and adds up the payoffs. Rock-Paper-Scissors, Matching Pennies, the
Prisoner's Dilemma and the Stag Hunt are one class each, with a different
table.

Simultaneous moves as hidden sequential moves
---------------------------------------------
The engine moves one seat at a time. Following OpenSpiel's
``turn_based_simultaneous_game`` idea, a round is two moves in a row:

1. seat 0 *commits* to an action. It stays hidden (``MatrixState.committed``).
2. seat 1 commits without seeing it. Now both are revealed and paid.

Seat 1's information set therefore contains every possible commit of seat 0,
which is exactly what "at the same time" means. The first commit is private in
the move log (:meth:`MatrixGame.privacy`), the scene never shows it to seat 1
and the rule cards below only read *revealed* rounds.

The math of tables
------------------
The module-level functions are plain numpy and named after the concepts, so
the lens and the tests read like a textbook. ``A[i, j]`` is the row player's
payoff and ``B[i, j]`` the column player's, when row plays ``i`` and column
plays ``j``:

=============================  ===============================================
:func:`best_responses`         the actions that do best against a fixed mix
:func:`pure_equilibria`        cells where both are best responses
:func:`solve_2x2`              the mixed equilibrium of a 2x2 game, closed form
:func:`support_enumeration`    every equilibrium of a small game
:func:`zero_sum_value`         what a player can guarantee (maximin value)
:func:`exploitability`         how far a mix falls below that guarantee
:func:`nash_gap`               how much both players could gain by deviating
:func:`dominated_by`           pure-strategy dominance
=============================  ===============================================

Rule cards every matrix game shares: ``copy``, ``hunt``, ``mix``, ``wsls``
and ``outthink``. Subclasses add the constant and game-specific ones.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from functools import cached_property
from typing import ClassVar, Sequence

import numpy as np

from strategy_lab.core import Game, Model, Param, pick, scene
from strategy_lab.core.game import Action

#: Numeric tolerance for ties and for "is this probability zero".
TOL = 1e-9


# --------------------------------------------------------------------------- #
# The math of payoff tables
# --------------------------------------------------------------------------- #
def payoff_arrays(table: Sequence[Sequence[Sequence[float]]]) -> tuple[np.ndarray, np.ndarray]:
    """Split ``table[i][j] = (row payoff, column payoff)`` into ``A`` and ``B``."""
    arr = np.array(table, dtype=float)
    return arr[:, :, 0], arr[:, :, 1]


def best_responses(values: Sequence[float], tol: float = TOL) -> list[int]:
    """Indices of the largest entries of ``values`` (ties within ``tol``).

    ``values[i]`` is the expected payoff of action ``i`` against a fixed
    opponent mix. Every action returned is a *best response* to that mix.
    """
    best = max(values)
    return [i for i, v in enumerate(values) if v >= best - tol]


def pure_equilibria(A: np.ndarray, B: np.ndarray) -> list[tuple[int, int]]:
    """Cells ``(i, j)`` where each action is a best response to the other.

    Nobody gains by changing only their own action: a pure Nash equilibrium.
    """
    out = []
    for i in range(A.shape[0]):
        for j in range(A.shape[1]):
            row_ok = A[i, j] >= A[:, j].max() - TOL
            col_ok = B[i, j] >= B[i, :].max() - TOL
            if row_ok and col_ok:
                out.append((i, j))
    return out


def solve_2x2(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """The fully mixed equilibrium of a 2x2 game in closed form, or ``None``.

    The column player's probability ``q`` of action 0 must make the row
    player indifferent between both rows::

        A00 q + A01 (1 - q) = A10 q + A11 (1 - q)

    which gives ``q = (A11 - A01) / (A00 - A01 - A10 + A11)``. The row
    player's ``p`` follows the same way from ``B``. Returns ``None`` when a
    denominator is zero or a probability falls outside ``(0, 1)``.
    """
    da = A[0, 0] - A[0, 1] - A[1, 0] + A[1, 1]
    db = B[0, 0] - B[0, 1] - B[1, 0] + B[1, 1]
    if abs(da) < TOL or abs(db) < TOL:
        return None
    q = (A[1, 1] - A[0, 1]) / da
    p = (B[1, 1] - B[1, 0]) / db
    if not (TOL < p < 1 - TOL and TOL < q < 1 - TOL):
        return None
    return np.array([p, 1 - p]), np.array([q, 1 - q])


@dataclass(frozen=True)
class Equilibrium:
    """A Nash equilibrium: one probability vector per seat."""

    row: tuple[float, ...]
    col: tuple[float, ...]

    @property
    def pure(self) -> bool:
        """True if both players play a single action."""
        return max(self.row) > 1 - TOL and max(self.col) > 1 - TOL

    def payoffs(self, A: np.ndarray, B: np.ndarray) -> tuple[float, float]:
        """Expected payoff of both players at this equilibrium."""
        p, q = np.array(self.row), np.array(self.col)
        return float(p @ A @ q), float(p @ B @ q)


def _indifference(M: np.ndarray, rows: Sequence[int], cols: Sequence[int]):
    """Mix ``x`` on ``cols`` that pays every row in ``rows`` the same, or ``None``.

    Solves ``M[rows, cols] x = v`` together with ``sum(x) = 1`` for ``(x, v)``.
    """
    k = len(rows)
    system = np.zeros((k + 1, k + 1))
    system[:k, :k] = M[np.ix_(list(rows), list(cols))]
    system[:k, k] = -1.0
    system[k, :k] = 1.0
    rhs = np.zeros(k + 1)
    rhs[k] = 1.0
    try:
        solution = np.linalg.solve(system, rhs)
    except np.linalg.LinAlgError:
        return None
    return solution[:k], float(solution[k])


def _equilibrium_on_supports(A: np.ndarray, B: np.ndarray, rows: Sequence[int],
                             cols: Sequence[int]) -> Equilibrium | None:
    """Try to build an equilibrium that plays exactly ``rows`` and ``cols``."""
    q_part = _indifference(A, rows, cols)       # makes the row player indifferent
    p_part = _indifference(B.T, cols, rows)     # makes the column player indifferent
    if q_part is None or p_part is None:
        return None
    (q_sup, v), (p_sup, w) = q_part, p_part
    if (q_sup < -TOL).any() or (p_sup < -TOL).any():
        return None
    p = np.zeros(A.shape[0])
    q = np.zeros(A.shape[1])
    p[list(rows)] = np.clip(p_sup, 0.0, None)
    q[list(cols)] = np.clip(q_sup, 0.0, None)
    # No action outside the support may pay more than the supported ones.
    if (A @ q).max() > v + 1e-7 or (p @ B).max() > w + 1e-7:
        return None
    return Equilibrium(tuple(float(x) for x in p), tuple(float(x) for x in q))


def support_enumeration(A: np.ndarray, B: np.ndarray,
                        max_actions: int = 6) -> list[Equilibrium]:
    """Every Nash equilibrium of a small bimatrix game.

    In a nondegenerate game both players mix over supports of the same size.
    For each pair of supports the indifference conditions are a linear system.
    A solution is an equilibrium if its probabilities are nonnegative and no
    action outside the supports does better. Pure equilibria are the supports
    of size 1. Costs ``sum_k C(m, k) C(n, k)`` small solves.

    Raises:
        ValueError: if a player has more than ``max_actions`` actions.
    """
    m, n = A.shape
    if max(m, n) > max_actions:
        raise ValueError(f"support enumeration is limited to {max_actions} actions")
    found: list[Equilibrium] = []
    for k in range(1, min(m, n) + 1):
        for rows in itertools.combinations(range(m), k):
            for cols in itertools.combinations(range(n), k):
                eq = _equilibrium_on_supports(A, B, rows, cols)
                if eq is None:
                    continue
                if any(np.allclose(eq.row, e.row, atol=1e-6) and np.allclose(eq.col, e.col, atol=1e-6)
                       for e in found):
                    continue
                found.append(eq)
    return found


def zero_sum_value(U: np.ndarray) -> float:
    """The maximin value of ``U``: what the row player can guarantee.

    It is the value of the zero-sum game ``(U, -U)``: the row player picks a
    mix, the column player answers with the reply that hurts most. All
    equilibria of a zero-sum game pay the same, so the first one is enough.
    """
    eqs = support_enumeration(U, -U)
    if not eqs:  # pragma: no cover - a finite zero-sum game always has one
        raise ValueError("no equilibrium found")
    return eqs[0].payoffs(U, -U)[0]


def exploitability(U: np.ndarray, mix: np.ndarray) -> float:
    """How far ``mix`` falls below the player's guaranteed value.

    ``U[i, j]`` is this player's payoff for own action ``i`` against opponent
    action ``j``. The worst case of a mix is what an opponent who knows it
    can hold you to: ``min_j (mix @ U)[j]``. Exploitability is the gap to the
    maximin value, so it is 0 for an equilibrium strategy of a zero-sum game
    and positive for every predictable one.
    """
    return zero_sum_value(U) - float((np.asarray(mix) @ U).min())


def nash_gap(A: np.ndarray, B: np.ndarray, p: np.ndarray, q: np.ndarray) -> float:
    """Total gain available by deviating alone: 0 exactly at an equilibrium.

    The row player could gain ``max(A q) - p A q`` by switching to a best
    response, the column player ``max(p B) - p B q``. The sum is the
    "NashConv" distance of the profile ``(p, q)`` from equilibrium.
    """
    row_gain = float((A @ q).max() - p @ A @ q)
    col_gain = float((p @ B).max() - p @ B @ q)
    return max(0.0, row_gain) + max(0.0, col_gain)


def dominated_by(U: np.ndarray, i: int, k: int) -> bool:
    """Is action ``i`` strictly worse than action ``k`` against every reply?"""
    return bool((U[k] > U[i] + TOL).all())


def entropy_bits(probs: Sequence[float]) -> float:
    """Shannon entropy ``-sum p log2 p`` in bits (0 for a certain action)."""
    return float(max(0.0, -sum(p * math.log2(p) for p in probs if p > TOL)))


def _num(x: float) -> str:
    """Format a payoff: ``3`` not ``3.0``, ``0.5`` as is."""
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


# --------------------------------------------------------------------------- #
# The game family
# --------------------------------------------------------------------------- #
@dataclass
class MatrixState:
    """The history of a repeated matrix game.

    Attributes:
        rounds: revealed rounds, oldest first, as ``(seat 0 action, seat 1 action)``.
        committed: seat 0's action in the round being played. Hidden until
            seat 1 has committed. ``None`` while seat 0 is to move.
        scores: cumulative payoff of each seat.
    """

    rounds: list[tuple[int, int]] = field(default_factory=list)
    committed: int | None = None
    scores: list[float] = field(default_factory=lambda: [0.0, 0.0])


class MatrixGame(Game):
    """Base class of the matrix-game family. See the module docstring.

    A subclass sets :attr:`action_names` and :attr:`payoff_table`, plus the
    usual metadata. Everything else (rules, scene, hidden commits, rule
    cards, equilibria) is inherited.
    """

    family_id = "matrix"
    family_name = "Matrix games"
    family_blurb = ("Everyone chooses at the same time and one payoff table decides. "
                    "There is no best move, only a best mix: Rock-Paper-Scissors, the "
                    "Prisoner's Dilemma and the Stag Hunt are one class with other numbers.")

    num_players = 2
    simultaneous = True
    perfect_information = False

    params = {
        "rounds": Param(10, "Rounds", "How many times the same game is played in a row. "
                                      "Your return is the sum of the round payoffs.",
                        min=1, max=100),
    }

    #: Action names of both seats (override :meth:`seat_actions` if they differ).
    action_names: ClassVar[tuple[str, ...]] = ()
    #: ``payoff_table[i][j] = (payoff of seat 0, payoff of seat 1)`` when seat 0
    #: plays action ``i`` and seat 1 plays action ``j``.
    payoff_table: ClassVar[tuple[tuple[tuple[float, float], ...], ...]] = ()

    models = (
        Model("last", "Last round only", "approx",
              state="the pair of moves revealed in the last round",
              actions="your moves",
              reward="your payoff each round, summed over the rounds",
              size="n x n states for n moves",
              transition="the table pays you at once, but the next state is whatever "
                         "the opponent plays: their policy is part of the environment",
              note="Enough against an opponent who only reacts to the last round (a "
                   "copycat). It fails against one who counts, like the frequency hunter."),
        Model("counts", "Move counts of both players", "approx",
              state="how often each player used each move so far",
              actions="your moves",
              reward="your payoff each round, summed over the rounds",
              size="grows with the rounds, but much slower than the full history",
              transition="the opponent's policy decides how the counts change",
              note="A sufficient summary for an opponent who plays a fixed mix. The order "
                   "of the moves is lost, so a cycling opponent looks random."),
        Model("history", "Full history of rounds", True,
              state="every revealed round in order",
              actions="your moves",
              reward="your payoff each round, summed over the rounds",
              size="(n x n)^t after t rounds",
              transition="the opponent's policy maps this history to their next move",
              note="Always Markov, and the state space grows with every round. "
                   "Practical agents compress it."),
    )

    def __init__(self, **params) -> None:
        super().__init__(**params)
        #: ``A[i, j]``: payoff of seat 0 (the row player).
        #: ``B[i, j]``: payoff of seat 1 (the column player).
        self.A, self.B = payoff_arrays(self.payoff_table)

    # ------------------------------------------------------------------ seats
    def seat_actions(self, seat: int) -> tuple[str, ...]:
        """Action names of ``seat``. Both seats share one list by default."""
        return self.action_names

    def utility_matrix(self, seat: int) -> np.ndarray:
        """``U[i, j]``: payoff of ``seat`` for own action ``i`` against their ``j``."""
        return self.A if seat == 0 else self.B.T

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> MatrixState:
        return MatrixState()

    def copy_state(self, s: MatrixState) -> MatrixState:
        return MatrixState(list(s.rounds), s.committed, list(s.scores))

    def current_player(self, s: MatrixState) -> int:
        return 0 if s.committed is None else 1

    def legal_actions(self, s: MatrixState) -> list[Action]:
        return list(range(len(self.seat_actions(self.current_player(s)))))

    def move(self, s: MatrixState, a: Action) -> None:
        if s.committed is None:
            s.committed = int(a)
            return
        a0, a1 = s.committed, int(a)
        u0, u1 = self.payoff_table[a0][a1]
        s.rounds.append((a0, a1))
        s.scores[0] += u0
        s.scores[1] += u1
        s.committed = None

    def is_terminal(self, s: MatrixState) -> bool:
        return len(s.rounds) >= self.p["rounds"]

    def returns(self, s: MatrixState) -> list[float]:
        return list(s.scores)

    # ----------------------------------------------------- what a seat may know
    def opponent_actions(self, s: MatrixState, player: int) -> list[int]:
        """The opponent's *revealed* actions, oldest first. Never the pending commit."""
        return [r[1 - player] for r in s.rounds]

    def own_actions(self, s: MatrixState, player: int) -> list[int]:
        """``player``'s own revealed actions, oldest first."""
        return [r[player] for r in s.rounds]

    def empirical_mix(self, actions: Sequence[int], n_actions: int) -> np.ndarray | None:
        """Relative frequency of each action in ``actions``; ``None`` if empty."""
        if not actions:
            return None
        return np.bincount(actions, minlength=n_actions) / len(actions)

    def opponent_mix(self, s: MatrixState, player: int) -> np.ndarray | None:
        """How often the opponent played each action so far."""
        return self.empirical_mix(self.opponent_actions(s, player),
                                  len(self.seat_actions(1 - player)))

    def own_mix(self, s: MatrixState, player: int) -> np.ndarray | None:
        """How often ``player`` played each action so far (what the opponent has seen)."""
        return self.empirical_mix(self.own_actions(s, player),
                                  len(self.seat_actions(player)))

    def best_replies(self, seat: int, opponent_mix: np.ndarray) -> list[int]:
        """The actions of ``seat`` that are best responses to ``opponent_mix``."""
        return best_responses(self.utility_matrix(seat) @ opponent_mix)

    def observation(self, s: MatrixState, player: int) -> str:
        """Revealed rounds, plus your own commit. Never the other seat's commit."""
        first, second = self.seat_actions(0), self.seat_actions(1)
        rounds = ", ".join(f"{first[a]}/{second[b]}" for a, b in s.rounds) or "none"
        text = f"revealed rounds: {rounds}"
        if player == 0 and s.committed is not None:
            text += f"; you committed {first[s.committed]}"
        return text

    # ------------------------------------------------------------ equilibria
    @cached_property
    def equilibria(self) -> list[Equilibrium]:
        """All Nash equilibria of one round (pure first, then mixed)."""
        return support_enumeration(self.A, self.B)

    def reference_equilibrium(self) -> Equilibrium:
        """The equilibrium the ``mix`` card plays: the mixed one if there is one."""
        mixed = [e for e in self.equilibria if not e.pure]
        return (mixed or self.equilibria)[0]

    def equilibrium_mix(self, seat: int) -> np.ndarray:
        """``seat``'s probabilities in the reference equilibrium."""
        eq = self.reference_equilibrium()
        return np.array(eq.row if seat == 0 else eq.col)

    # ---------------------------------------------------------- rule cards
    @property
    def same_actions(self) -> bool:
        """Do both seats choose from lists of equal size (so "copy" makes sense)?"""
        return len(self.seat_actions(0)) == len(self.seat_actions(1))

    def _pick_from(self, actions: Sequence[int], candidates: list[Action], rng):
        """A random action of ``actions`` that is still a candidate, or ``None``."""
        options = [a for a in actions if a in candidates]
        return rng.choice(options) if options else None

    @pick("copy", "Copy their last move",
          "Play whatever they played last round. In round 1 there is nothing to copy.", "mirror")
    def card_copy(self, s, candidates, player, rng):
        theirs = self.opponent_actions(s, player)
        if not theirs or not self.same_actions:
            return None
        return theirs[-1] if theirs[-1] in candidates else None

    @pick("hunt", "Hunt their habit",
          "Count how often they played each move, then play the best answer to that mix.",
          "target")
    def card_hunt(self, s, candidates, player, rng):
        mix = self.opponent_mix(s, player)
        if mix is None:
            return None
        return self._pick_from(self.best_replies(player, mix), candidates, rng)

    @pick("mix", "Play the equilibrium mix",
          "Roll the dice with the Nash probabilities. Nobody can read a pattern that is not there.",
          "dice")
    def card_mix(self, s, candidates, player, rng):
        probs = self.equilibrium_mix(player)
        weights = [float(probs[a]) for a in candidates]
        return rng.choices(candidates, weights=weights)[0] if sum(weights) > 0 else None

    @pick("wsls", "Win-stay, lose-shift",
          "Repeat your last move if it paid more than average. If not, switch to the next one.",
          "shuffle")
    def card_wsls(self, s, candidates, player, rng):
        mine = self.own_actions(s, player)
        if not mine:
            return None
        U = self.utility_matrix(player)
        a, b = s.rounds[-1][player], s.rounds[-1][1 - player]
        if U[a, b] > U.mean() + TOL:
            nxt = a
        else:
            nxt = (a + 1) % U.shape[0]
        return nxt if nxt in candidates else None

    @pick("outthink", "Think a level deeper",
          "They study your habits. Predict their answer to those habits, then play the best "
          "reply to that answer.", "brain")
    def card_outthink(self, s, candidates, player, rng):
        mine = self.own_mix(s, player)
        if mine is None:
            return None
        their_replies = self.best_replies(1 - player, mine)
        belief = np.zeros(len(self.seat_actions(1 - player)))
        belief[their_replies] = 1.0 / len(their_replies)
        return self._pick_from(self.best_replies(player, belief), candidates, rng)

    # ------------------------------------------------------------ presentation
    def action_label(self, s: MatrixState, a: Action) -> str:
        return self.seat_actions(self.current_player(s))[int(a)]

    def outcome_text(self, a0: int, a1: int) -> str:
        """How the log words the result of one round (subclasses may refine it)."""
        u0, u1 = self.payoff_table[a0][a1]
        if u0 == u1:
            return f"both get {_num(u0)}"
        if u0 + u1 == 0:
            winner = 0 if u0 > u1 else 1
            return f"{self.seat_label(winner)} wins (+{_num(abs(u0))})"
        return f"{self.seat_label(0)} gets {_num(u0)}, {self.seat_label(1)} gets {_num(u1)}"

    def describe(self, s: MatrixState, a: Action, player: int) -> str:
        mine = self.seat_actions(player)[int(a)]
        if s.committed is None:
            return f"commits to {mine}"
        theirs = self.seat_actions(1 - player)[s.committed]
        return f"plays {mine} vs {theirs}: {self.outcome_text(s.committed, int(a))}"

    def privacy(self, s: MatrixState, a: Action, player: int) -> tuple[int, ...] | None:
        """The first commit of a round is private; the second reveals the round."""
        return (player,) if s.committed is None else None

    def describe_hidden(self, s: MatrixState, a: Action, player: int) -> str:
        return "commits a choice"

    def status(self, s: MatrixState, viewer: int | None) -> str:
        total = self.p["rounds"]
        if self.is_terminal(s):
            a, b = s.scores
            tally = f"{_num(a)} to {_num(b)}"
            if a == b:
                return f"Game over: {tally}, a tie"
            return f"Game over: {tally}, {self.seat_label(0 if a > b else 1)} leads"
        number = len(s.rounds) + 1
        mover = self.current_player(s)
        if viewer is None:
            return f"Round {number} of {total}: {self.seat_label(mover)} chooses"
        if mover == viewer:
            return f"Round {number} of {total}: choose your move"
        return f"Round {number} of {total}: waiting for {self.seat_label(mover)}"

    def _view_payoff(self, me: int, i: int, j: int) -> list[float]:
        """Payoffs ``[mine, theirs]`` when I play ``i`` and they play ``j``."""
        if me == 0:
            return list(self.payoff_table[i][j])
        return list(reversed(self.payoff_table[j][i]))

    def scene(self, s: MatrixState, viewer: int | None) -> dict:
        me = 0 if viewer is None else viewer
        them = 1 - me
        mine, theirs = self.seat_actions(me), self.seat_actions(them)
        table = [[self._view_payoff(me, i, j) for j in range(len(theirs))]
                 for i in range(len(mine))]
        seen = [r if me == 0 else (r[1], r[0]) for r in s.rounds]
        can_act = viewer is not None and not self.is_terminal(s) \
            and self.current_player(s) == viewer
        matrix = scene.matrix(
            mine, theirs, table, row_player=me, col_player=them,
            row_actions=list(range(len(mine))) if can_act else [],
            highlight=seen[-1] if seen else None, history=seen[:-1],
            caption=self._caption(s))
        rows = []
        for seat in (0, 1):
            name = self.seat_label(seat) + (" (you)" if seat == viewer else "")
            rows.append(scene.player(name, score=_num(s.scores[seat]),
                                     sub=self._player_note(s, seat, viewer), owner=seat,
                                     active=not self.is_terminal(s)
                                     and self.current_player(s) == seat))
        return scene.scene([matrix], players=rows, status=self.status(s, viewer))

    def _player_note(self, s: MatrixState, seat: int, viewer: int | None) -> str:
        if seat == 0 and viewer == 0 and s.committed is not None:
            return f"locked in {self.seat_actions(0)[s.committed]}"
        if s.rounds:
            return f"last: {self.seat_actions(seat)[s.rounds[-1][seat]]}"
        return ""

    def _caption(self, s: MatrixState) -> str:
        if not s.rounds:
            return "Rows are your moves, columns are theirs. Each cell: your payoff, then theirs."
        a, b = s.rounds[-1]
        return (f"Last round: {self.seat_label(0)} played {self.seat_actions(0)[a]}, "
                f"{self.seat_label(1)} played {self.seat_actions(1)[b]}: "
                f"{self.outcome_text(a, b)}.")
