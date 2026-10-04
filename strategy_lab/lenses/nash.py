"""The Nash lens: what does game theory say about this payoff table?

For a matrix game (see :class:`~strategy_lab.families.matrix.MatrixGame`)
the lens shows the table and answers the classic questions:

* Which cells are **pure Nash equilibria** (nobody gains by switching alone)?
* Is there a **mixed equilibrium**, and what are its probabilities? (Closed
  form for 2x2 games, support enumeration with numpy for small bigger ones.)
* Is a strategy **dominant** (best against everything) or **dominated**
  (never best)? What survives repeated elimination of dominated strategies?
* How have *you* played so far? Your empirical mix, its **entropy** in bits
  (maximum ``log2(n)``) and its **exploitability**: how much a player who
  knows your mix could take from you compared with what you can guarantee.
* What is the **best response** to how the opponent has played so far, and
  what does each of your moves earn against that mix? (Shown on the board.)
* **Regret matching**: both seats learn by self-play, each round playing
  actions in proportion to the regret of not having played them. The
  *average* strategies move toward equilibrium in zero-sum games. The lens
  sends the whole trajectory so the page can plot the convergence.

"You" is the first human seat, or seat 0 when nobody is human.

Option: ``iterations`` of the regret-matching self-play.

Result schema (seat order is always ``[seat 0, seat 1]``)::

    {
      "seats":   ["Player 1", "Player 2"],
      "me":      <seat>,
      "rounds":  <rounds revealed so far>, "totalRounds": <int>,
      "labels":  [[seat 0 action names], [seat 1 action names]],
      "payoffs": [[[u0, u1], ...], ...],       # payoffs[i][j], i = seat 0's action
      "zeroSum": <bool>,
      "pure":    [{"cell": [i, j], "labels": [name0, name1], "payoffs": [u0, u1]}],
      "equilibria": [{"row": [p...], "col": [q...], "pure": <bool>,
                      "payoffs": [u0, u1],
                      "method": "best response" | "closed form" | "support enumeration"}],
      "dominance": {"dominant": [<action or null>, <action or null>],
                    "dominated": [[{"action", "by"}], [{"action", "by"}]],
                    "survivors": [[<actions>], [<actions>]]},
      "empirical": {"counts": [[..], [..]], "freq": [[..] | null, [..] | null]},
      "you":     null | {"seat", "freq", "entropy", "maxEntropy", "predictability",
                         "exploitability", "guarantee", "bestResponse": [<actions>],
                         "bestResponseLabels": [...], "expected": [per own action]},
      "overlay": {"actions": {"<own action>": {"text", "tone", "value"}}},
      "regret":  {"iterations": N,
                  "points": [{"t", "row": [..], "col": [..], "gap"}],
                  "equilibrium": null | {"row": [..], "col": [..]}}
    }

``"you"`` and the overlay are ``null`` / empty until the opponent has played a
revealed round. Actions are the integer indices used by the game.
"""

from __future__ import annotations

import numpy as np

from strategy_lab.families.matrix import (
    TOL, MatrixGame, dominated_by, entropy_bits, exploitability, nash_gap,
    solve_2x2, support_enumeration, zero_sum_value,
)
from strategy_lab.lenses.base import Lens, overlay


def positive_part_strategy(regrets: np.ndarray) -> np.ndarray:
    """Regret matching: play each action in proportion to its positive regret.

    With no positive regret, play uniformly.
    """
    positive = np.maximum(regrets, 0.0)
    total = positive.sum()
    return positive / total if total > TOL else np.full(len(regrets), 1.0 / len(regrets))


def regret_matching(A: np.ndarray, B: np.ndarray, iterations: int, points: int = 60):
    """Self-play regret matching with exact expected payoffs (deterministic).

    Each iteration both players play their current mixed strategy. The regret
    of an action is how much more it would have paid against the opponent's
    current mix than the strategy actually played. Start: row plays its first
    action and column its second, so there is something to learn from.

    Returns:
        A list of checkpoints ``{"t", "row", "col", "gap"}`` where ``row`` and
        ``col`` are the *average* strategies up to iteration ``t`` and
        ``gap`` is :func:`~strategy_lab.families.matrix.nash_gap` of that pair.
    """
    m, n = A.shape
    x = np.zeros(m)
    x[0] = 1.0
    y = np.zeros(n)
    y[1 % n] = 1.0
    regret_row, regret_col = np.zeros(m), np.zeros(n)
    sum_x, sum_y = np.zeros(m), np.zeros(n)
    marks = {int(t) for t in np.unique(np.round(np.geomspace(1, iterations, points)))}
    out = []
    for t in range(1, iterations + 1):
        sum_x += x
        sum_y += y
        row_payoffs, col_payoffs = A @ y, x @ B
        regret_row += row_payoffs - x @ row_payoffs
        regret_col += col_payoffs - y @ col_payoffs
        if t in marks:
            avg_x, avg_y = sum_x / t, sum_y / t
            out.append({"t": t, "row": [round(float(v), 4) for v in avg_x],
                        "col": [round(float(v), 4) for v in avg_y],
                        "gap": round(nash_gap(A, B, avg_x, avg_y), 5)})
        x, y = positive_part_strategy(regret_row), positive_part_strategy(regret_col)
    return out


def dominance(game: MatrixGame) -> dict:
    """Dominant strategies, dominated strategies and what iterated elimination leaves."""
    utilities = [game.utility_matrix(0), game.utility_matrix(1)]
    sizes = [u.shape[0] for u in utilities]
    dominant: list[int | None] = [None, None]
    dominated: list[list[dict]] = [[], []]
    for seat in (0, 1):
        U = utilities[seat]
        for k in range(sizes[seat]):
            if all(dominated_by(U, i, k) for i in range(sizes[seat]) if i != k):
                dominant[seat] = k
        for i in range(sizes[seat]):
            by = next((k for k in range(sizes[seat]) if k != i and dominated_by(U, i, k)), None)
            if by is not None:
                dominated[seat].append({"action": i, "by": by})
    alive = [list(range(sizes[0])), list(range(sizes[1]))]
    changed = True
    while changed:
        changed = False
        for seat in (0, 1):
            other = 1 - seat
            U = utilities[seat][np.ix_(alive[seat], alive[other])]
            for action in list(alive[seat]):
                local = alive[seat].index(action)
                if len(alive[seat]) > 1 and any(
                        k != local and dominated_by(U, local, k) for k in range(len(alive[seat]))):
                    alive[seat].remove(action)
                    changed = True
                    break
    return {"dominant": dominant, "dominated": dominated, "survivors": alive}


class NashLens(Lens):
    id = "nash"
    title = "Nash"
    icon = "scale"
    blurb = "Equilibria, dominance and how predictable you are."
    concepts = ("nash-equilibrium", "best-response", "dominant-strategy", "mixed-strategy",
                "exploitability", "regret", "entropy", "zero-sum", "repeated-game")
    order = 30
    options = (
        {"name": "iterations", "label": "Regret-matching rounds", "type": "int",
         "default": 500, "min": 10, "max": 20000, "step": 100},
    )

    def applies(self, game) -> bool:
        return isinstance(game, MatrixGame)

    # ------------------------------------------------------------------ run
    def run(self, session, options):
        g, s = session.game, session.state
        me = (session.human_seats() or [0])[0]
        A, B = g.A, g.B
        counts = [np.bincount([r[seat] for r in s.rounds], minlength=len(g.seat_actions(seat)))
                  for seat in (0, 1)]
        freq = [c / c.sum() if c.sum() else None for c in counts]
        equilibria = self._equilibria(g)
        you, ov = self._you(g, s, me, counts)
        iterations = self.option(options, "iterations")
        return {
            "seats": [g.seat_label(0), g.seat_label(1)], "me": me,
            "rounds": len(s.rounds), "totalRounds": g.p["rounds"],
            "labels": [list(g.seat_actions(0)), list(g.seat_actions(1))],
            "payoffs": [[list(map(float, cell)) for cell in row] for row in g.payoff_table],
            "zeroSum": bool(np.allclose(A + B, 0.0)),
            "pure": self._pure(g),
            "equilibria": equilibria,
            "dominance": dominance(g),
            "empirical": {"counts": [c.tolist() for c in counts],
                          "freq": [None if f is None else [round(float(v), 4) for v in f]
                                   for f in freq]},
            "you": you, "overlay": ov,
            "regret": {"iterations": iterations, "points": regret_matching(A, B, iterations),
                       "equilibrium": self._reference(g)},
        }

    # ------------------------------------------------------------- sections
    @staticmethod
    def _pure(g: MatrixGame) -> list[dict]:
        from strategy_lab.families.matrix import pure_equilibria
        return [{"cell": [i, j], "labels": [g.seat_actions(0)[i], g.seat_actions(1)[j]],
                 "payoffs": [float(g.A[i, j]), float(g.B[i, j])]}
                for i, j in pure_equilibria(g.A, g.B)]

    @staticmethod
    def _equilibria(g: MatrixGame) -> list[dict]:
        try:
            found = support_enumeration(g.A, g.B)
        except ValueError:
            return []
        closed = solve_2x2(g.A, g.B) if g.A.shape == (2, 2) else None
        out = []
        for eq in found:
            if eq.pure:
                method = "best response"
            elif closed is not None and np.allclose(eq.row, closed[0], atol=1e-6):
                method = "closed form"
            else:
                method = "support enumeration"
            u0, u1 = eq.payoffs(g.A, g.B)
            out.append({"row": [round(v, 4) for v in eq.row],
                        "col": [round(v, 4) for v in eq.col], "pure": eq.pure,
                        "payoffs": [round(u0, 4), round(u1, 4)], "method": method})
        return out

    @staticmethod
    def _reference(g: MatrixGame) -> dict | None:
        try:
            eq = g.reference_equilibrium()
        except (ValueError, IndexError):
            return None
        return {"row": [round(v, 4) for v in eq.row], "col": [round(v, 4) for v in eq.col]}

    @staticmethod
    def _you(g: MatrixGame, s, me: int, counts: list[np.ndarray]):
        """Your habits and the best answer to the opponent's: ``(you, overlay)``."""
        opp = 1 - me
        if not s.rounds:
            return None, {"actions": {}}
        U = g.utility_matrix(me)
        mine = counts[me] / counts[me].sum()
        theirs = counts[opp] / counts[opp].sum()
        expected = U @ theirs
        best = [int(i) for i in g.best_replies(me, theirs)]
        try:
            guarantee = zero_sum_value(U)
            exploit = exploitability(U, mine)
        except ValueError:
            guarantee = exploit = None
        top = entropy_bits(np.ones(len(mine)) / len(mine))
        h = entropy_bits(mine)
        labels = g.seat_actions(me)
        you = {
            "seat": me, "freq": [round(float(v), 4) for v in mine],
            "entropy": round(h, 4), "maxEntropy": round(top, 4),
            "predictability": round(1.0 - h / top, 4) if top else 0.0,
            "exploitability": None if exploit is None else round(float(exploit), 4),
            "guarantee": None if guarantee is None else round(float(guarantee), 4),
            "bestResponse": best, "bestResponseLabels": [labels[i] for i in best],
            "expected": [round(float(v), 4) for v in expected],
        }
        return you, overlay({i: float(v) for i, v in enumerate(expected)})
