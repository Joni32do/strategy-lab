"""Game-tree search for two-player zero-sum games.

* :class:`Solver`: exact minimax / expectimax with a transposition table
  keyed by :meth:`~strategy_lab.core.game.Game.canonical_key`, so symmetric
  positions are solved once. Raises :class:`TooBig` past a node budget.
* :func:`alphabeta`: depth-limited search that falls back on the game's
  :meth:`~strategy_lab.core.game.Game.heuristic` at the horizon.
* :class:`SearchPolicy`: a bot built on either.

Values are always from **player 0's** point of view (``returns(s)[0]``):
player 0 maximizes, player 1 minimizes, chance averages.
"""

from __future__ import annotations

import math
import random
from typing import Any

from strategy_lab.core.game import CHANCE, Action, Game
from strategy_lab.core.policy import Policy


class TooBig(RuntimeError):
    """The tree has more distinct positions than the solver's budget."""


class Solver:
    """Exact game values with memoization. See the module docstring."""

    def __init__(self, game: Game, budget: int = 400_000):
        self.game = game
        self.budget = budget
        self.memo: dict[Any, float] = {}

    def value(self, s: Any) -> float:
        g = self.game
        if g.is_terminal(s):
            return float(g.returns(s)[0])
        k = g.canonical_key(s)
        v = self.memo.get(k)
        if v is not None:
            return v
        if len(self.memo) >= self.budget:
            raise TooBig(f"more than {self.budget} positions")
        p = g.current_player(s)
        if p == CHANCE:
            v = sum(prob * self.value(g.apply_action(s, a)) for a, prob in g.chance_outcomes(s))
        else:
            children = (self.value(g.apply_action(s, a)) for a in g.legal_actions(s))
            v = max(children) if p == 0 else min(children)
        self.memo[k] = v
        return v

    def action_values(self, s: Any) -> list[tuple[Action, float]]:
        """Value of each legal action, from the *mover's* point of view."""
        g = self.game
        sign = 1.0 if g.current_player(s) == 0 else -1.0
        return [(a, sign * self.value(g.apply_action(s, a))) for a in g.legal_actions(s)]


def alphabeta(game: Game, s: Any, depth: int, alpha: float = -math.inf,
              beta: float = math.inf) -> float:
    """Depth-limited minimax with alpha-beta pruning (player 0's view)."""
    if game.is_terminal(s):
        return float(game.returns(s)[0])
    if depth <= 0:
        h = game.heuristic(s, 0)
        return 0.0 if h is None else float(h)
    p = game.current_player(s)
    if p == CHANCE:
        return sum(prob * alphabeta(game, game.apply_action(s, a), depth - 1)
                   for a, prob in game.chance_outcomes(s))
    if p == 0:
        best = -math.inf
        for a in game.legal_actions(s):
            best = max(best, alphabeta(game, game.apply_action(s, a), depth - 1, alpha, beta))
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best
    best = math.inf
    for a in game.legal_actions(s):
        best = min(best, alphabeta(game, game.apply_action(s, a), depth - 1, alpha, beta))
        beta = min(beta, best)
        if alpha >= beta:
            break
    return best


class SearchPolicy(Policy):
    """Plays the best action found by search; ties are broken at random.

    ``depth=None`` solves exactly (small games only). ``mistakes`` is the
    probability of playing a random move instead: a handy difficulty knob.
    """

    def __init__(self, depth: int | None = None, mistakes: float = 0.0,
                 name: str = "search", budget: int = 400_000):
        self.depth = depth
        self.mistakes = mistakes
        self.name = name
        self.budget = budget
        self._solvers: dict[int, Solver] = {}

    def values(self, game: Game, s: Any) -> list[tuple[Action, float]]:
        if self.depth is None:
            solver = self._solvers.setdefault(id(game), Solver(game, self.budget))
            return solver.action_values(s)
        sign = 1.0 if game.current_player(s) == 0 else -1.0
        return [(a, sign * alphabeta(game, game.apply_action(s, a), self.depth - 1))
                for a in game.legal_actions(s)]

    def act(self, game, s, player, rng: random.Random):
        legal = game.legal_actions(s)
        if len(legal) == 1:
            return legal[0]
        if self.mistakes and rng.random() < self.mistakes:
            return rng.choice(legal)
        vals = self.values(game, s)
        best = max(v for _, v in vals)
        return rng.choice([a for a, v in vals if v >= best - 1e-9])
