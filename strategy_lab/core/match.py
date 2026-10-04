"""Matches: play many games between policies and collect statistics.

One game is a quick loop over :class:`~strategy_lab.core.game.Game` without
logging. A match plays ``n`` games and rotates the seats each game, so
whoever moves first changes, and attributes every result back to the
policy (not the seat). This is the "simulate 100 games" button.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

from strategy_lab.core.game import CHANCE, Game
from strategy_lab.core.policy import Policy


@dataclass
class GameRecord:
    """Result of one simulated game, indexed by *policy*, not seat."""

    returns: list[float]
    winner: int | None
    first: int
    steps: int
    timeout: bool

    def to_json(self) -> dict:
        return {"returns": self.returns, "winner": self.winner, "first": self.first,
                "steps": self.steps, "timeout": self.timeout}


def play_out(game: Game, policies: Sequence[Policy], seed: int | str,
             state=None, max_steps: int | None = None) -> tuple[list[float], int, bool]:
    """Play from ``state`` (default: the start) to the end.

    ``policies[seat]`` acts for each seat. Returns ``(returns, steps, timeout)``.
    """
    rng = random.Random(seed)
    s = game.initial_state() if state is None else state
    cap = game.max_steps if max_steps is None else max_steps
    steps = 0
    while not game.is_terminal(s):
        if steps >= cap:
            return list(game.timeout_returns(s)), steps, True
        p = game.current_player(s)
        if p == CHANCE:
            a = game.sample_chance(s, rng)
        else:
            a = policies[p].act(game, s, p, rng)
        s = game.apply_action(s, a)
        steps += 1
    return list(game.returns(s)), steps, False


def _winner(returns: list[float]) -> int | None:
    best = max(returns)
    tops = [i for i, r in enumerate(returns) if r == best]
    return tops[0] if len(tops) == 1 else None


@dataclass
class MatchResult:
    """All games of a match plus totals per policy."""

    names: list[str]
    games: list[GameRecord] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.games)

    def wins(self, i: int) -> int:
        return sum(1 for g in self.games if g.winner == i)

    def draws(self) -> int:
        return sum(1 for g in self.games if g.winner is None)

    def mean_return(self, i: int) -> float:
        return sum(g.returns[i] for g in self.games) / max(1, self.n)

    def to_json(self) -> dict:
        k = len(self.names)
        first_split = []
        for i in range(k):
            started = [g for g in self.games if g.first == i]
            first_split.append({"games": len(started),
                                "wins": sum(1 for g in started if g.winner == i)})
        return {
            "names": self.names, "n": self.n,
            "wins": [self.wins(i) for i in range(k)], "draws": self.draws(),
            "meanReturns": [round(self.mean_return(i), 4) for i in range(k)],
            "timeouts": sum(1 for g in self.games if g.timeout),
            "firstMover": first_split,
            "games": [g.to_json() for g in self.games],
        }


def simulate(game: Game, policies: Sequence[Policy], n: int = 100, seed: int = 0,
             names: Sequence[str] | None = None, rotate: bool = True) -> MatchResult:
    """Play ``n`` games. With ``rotate``, game ``i`` seats policy ``(seat + i) % k``.

    With more seats than policies (a 4-player game, 2 policies), the extra
    seats repeat the last policy (your stack against three copies of a bot).
    """
    k = game.num_players
    pols = list(policies)
    while len(pols) < k:
        pols.append(pols[-1])
    distinct = len(policies)
    result = MatchResult(list(names) if names else [p.name for p in policies])
    for i in range(n):
        shift = i % k if rotate else 0
        # seat -> policy index
        order = [(seat + shift) % k for seat in range(k)]
        seated = [pols[j] for j in order]
        rets, steps, timeout = play_out(game, seated, f"{seed}:{i}")
        per_policy = [float("-inf")] * distinct
        for seat, j in enumerate(order):
            idx = min(j, distinct - 1)
            per_policy[idx] = max(per_policy[idx], rets[seat])
        result.games.append(GameRecord(per_policy, _winner(per_policy),
                                       min(order[0], distinct - 1), steps, timeout))
    return result
