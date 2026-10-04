"""Policies: anything that picks an action for a seat.

A policy is the formal word for a strategy: a rule that maps what a player
knows to what they do. The lab compares several ways to write one down:

* :class:`RulePolicy`: an ordered stack of readable rule cards.
* :class:`MixedPolicy`: fixed probabilities (mixed strategies, Nash).
* :class:`SearchPolicy` (in :mod:`strategy_lab.core.search`): look ahead.
* :class:`FunctionPolicy`: any Python callable, e.g. a trained table.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Sequence

from strategy_lab.core.game import Action, Card, Game


class Policy:
    """Base class. Subclasses implement :meth:`act`."""

    name = "policy"

    def act(self, game: Game, s: Any, player: int, rng: random.Random) -> Action:
        raise NotImplementedError

    def trace(self, game: Game, s: Any, player: int) -> dict:
        """Explain the decision in ``s`` (for the cards lens). Optional."""
        return {}


class RandomPolicy(Policy):
    name = "random"

    def act(self, game, s, player, rng):
        return rng.choice(game.legal_actions(s))


class FunctionPolicy(Policy):
    """Wrap ``fn(game, state, player, rng) -> action``."""

    def __init__(self, fn: Callable, name: str = "function"):
        self.fn = fn
        self.name = name

    def act(self, game, s, player, rng):
        return self.fn(game, s, player, rng)


class MixedPolicy(Policy):
    """Play each action with a fixed probability (a mixed strategy).

    ``probs`` maps actions to weights; illegal actions are ignored and the
    rest renormalized.
    """

    def __init__(self, probs: dict[Action, float], name: str = "mixed"):
        self.probs = dict(probs)
        self.name = name

    def act(self, game, s, player, rng):
        legal = game.legal_actions(s)
        weights = [max(0.0, self.probs.get(a, 0.0)) for a in legal]
        if sum(weights) <= 0:
            return rng.choice(legal)
        return rng.choices(legal, weights=weights)[0]


class RulePolicy(Policy):
    """An ordered stack of rule cards, read top to bottom each turn.

    Semantics (unchanged from the original Strategy Lab engine):

    1. Start with all legal actions as candidates.
    2. An AVOID card removes the candidates it vetoes, unless that would
       remove all of them.
    3. The first PICK card that returns an action decides.
    4. If no card decides: the only candidate left, or a random one.
    """

    def __init__(self, cards: Sequence[Card], name: str = "rule stack"):
        self.cards = list(cards)
        self.name = name

    def decide(self, game: Game, s: Any, player: int, rng: random.Random) -> dict:
        """Run the stack. Returns ``{"action", "card", "reason", "vetoed"}``.

        ``reason`` is ``"card"``, ``"forced"`` (one candidate left) or
        ``"random"``. ``vetoed`` lists ``(card id, [actions])`` removals.
        """
        candidates = list(game.legal_actions(s))
        if not candidates:
            raise ValueError(f"{game.id}: no legal actions for player {player}")
        vetoed: list[tuple[str, list]] = []
        for card in self.cards:
            if len(candidates) == 1:
                break
            if card.kind == "avoid":
                kept = [a for a in candidates if not card.fn(game, s, a, player)]
                if kept and len(kept) < len(candidates):
                    vetoed.append((card.id, [a for a in candidates if a not in kept]))
                    candidates = kept
            else:
                a = card.fn(game, s, candidates, player, rng)
                if a is not None:
                    if a not in candidates:
                        raise ValueError(f"{game.id}: card {card.id!r} picked {a!r}, "
                                         f"which is not a candidate")
                    return {"action": a, "card": card.id, "reason": "card", "vetoed": vetoed}
        if len(candidates) == 1:
            return {"action": candidates[0], "card": None, "reason": "forced",
                    "vetoed": vetoed}
        return {"action": rng.choice(candidates), "card": None, "reason": "random",
                "vetoed": vetoed, "candidates": candidates}

    def act(self, game, s, player, rng):
        return self.decide(game, s, player, rng)["action"]

    def trace(self, game, s, player):
        # A fixed RNG: a hint must not consume the game's randomness.
        return self.decide(game, s, player, random.Random(20260710))
