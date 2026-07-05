"""The tunable Catan policy the `high-level` Catan lens designs.

This is deliberately small and readable: a position-strength value function
whose three components (victory points, production, expansion) are blended by
weights you set from the terminal, plus a logistic trade coefficient. The point
of the lab is that moving a slider changes how the bot plays and, over a batch,
how often it wins -- so the metric has to be simple enough to reason about.

Nothing here is UI-aware; it only touches the real catanatron engine.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from catanatron.models.player import Player
from catanatron.models.enums import ActionType, SETTLEMENT, CITY
from catanatron.models.map import number_probability
from catanatron.state_functions import (
    get_actual_victory_points,
    get_visible_victory_points,
    get_player_buildings,
)


@dataclass
class Weights:
    """Position-strength weights (mirrors the sliders in the terminal)."""

    vp: float = 0.6
    production: float = 0.25
    expansion: float = 0.15
    prod_norm: float = 12.0
    expansion_norm: float = 8.0

    @classmethod
    def from_json(cls, d):
        d = d or {}
        base = cls()
        return cls(
            vp=float(d.get("vp", base.vp)),
            production=float(d.get("production", base.production)),
            expansion=float(d.get("expansion", base.expansion)),
            prod_norm=float(d.get("prod_norm", base.prod_norm)),
            expansion_norm=float(d.get("expansion_norm", base.expansion_norm)),
        )


@dataclass
class TradeParams:
    """The non-linear trade coefficient lambda(opp_strength) and its guards."""

    lam_max: float = 2.5
    lam_steepness: float = 8.0
    lam_midpoint: float = 0.5
    veto_vp_margin: float = 1.0
    margin: float = 0.15
    premium_per_vp: float = 0.5
    scarcity_weight: float = 1.0
    need_weight: float = 1.5
    base_value: float = 0.5

    @classmethod
    def from_json(cls, d):
        d = d or {}
        base = cls()
        out = cls()
        for f in base.__dataclass_fields__:
            out.__dict__[f] = float(d.get(f, getattr(base, f)))
        return out

    def lam(self, opp_strength: float) -> float:
        z = self.lam_steepness * (opp_strength - self.lam_midpoint)
        return self.lam_max / (1.0 + math.exp(-z))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def production_pips(state, color) -> float:
    """Expected resource pips: settlements count once, cities twice."""
    total = 0.0
    board = state.board
    for building_type, weight in ((SETTLEMENT, 1.0), (CITY, 2.0)):
        for node_id in get_player_buildings(state, color, building_type):
            for tile in board.map.adjacent_tiles[node_id]:
                if tile.number is not None:
                    total += weight * number_probability(tile.number)
    return total


def buildable_reach(state, color) -> int:
    try:
        return len(state.board.buildable_node_ids(color))
    except Exception:
        return 0


# Costs in freqdeck order [wood, brick, sheep, wheat, ore].
_COSTS = {
    "road": [1, 1, 0, 0, 0],
    "settlement": [1, 1, 1, 1, 0],
    "city": [0, 0, 0, 2, 3],
    "dev": [0, 0, 1, 1, 1],
}


def hand_readiness(state, color) -> float:
    """How many of the four builds the current hand can afford, as a 0..1 share.

    This gives the hand a gradient (so accumulating and trading *toward* a build
    is rewarded) without rewarding hoarding: it saturates once you can build.
    """
    from catanatron.state_functions import get_player_freqdeck

    hand = get_player_freqdeck(state, color)
    affordable = sum(
        1 for cost in _COSTS.values() if all(h >= c for h, c in zip(hand, cost))
    )
    return affordable / len(_COSTS)


def strength(state, color, w: Weights, vps_to_win: int = 10) -> float:
    """A position's strength in roughly [0, 1] -- our tunable value function."""
    vp = get_actual_victory_points(state, color)
    vp_c = _clamp01(vp / max(1, vps_to_win))
    prod_c = _clamp01(production_pips(state, color) / max(1e-6, w.prod_norm))
    exp_c = _clamp01(buildable_reach(state, color) / max(1e-6, w.expansion_norm))
    denom = w.vp + w.production + w.expansion
    blend = vp_c if denom <= 0 else (w.vp * vp_c + w.production * prod_c + w.expansion * exp_c) / denom
    # A small readiness bonus gives trades a purpose (turn surplus into a build)
    # without letting a full hand outweigh actual board position.
    return blend + 0.05 * hand_readiness(state, color)


def enemy_strength(state, color, w: Weights, vps_to_win: int = 10) -> float:
    best = 0.0
    for c in state.colors:
        if c != color:
            best = max(best, strength(state, c, w, vps_to_win))
    return best


@dataclass
class MetricPlayer(Player):
    """A value-function player driven by the tunable weights.

    On every decision it copies the game, plays each candidate action, scores
    the resulting position with `strength`, and keeps the best. Maritime trades
    are only considered when `enable_trade` is on, nudged by the logistic lambda
    so the bot barters more freely the stronger its opponent looks.
    """

    weights: Weights = field(default_factory=Weights)
    trade: TradeParams = field(default_factory=TradeParams)
    enable_trade: bool = True
    last_explanation: dict = field(default_factory=dict)
    maritime_trades: int = 0

    def __init__(self, color, weights=None, trade=None, enable_trade=True):
        super().__init__(color)
        self.weights = weights or Weights()
        self.trade = trade or TradeParams()
        self.enable_trade = enable_trade
        self.last_explanation = {}
        self.maritime_trades = 0

    def decide(self, game, playable_actions):
        actions = list(playable_actions)
        if not self.enable_trade:
            non_trade = [a for a in actions if a.action_type != ActionType.MARITIME_TRADE]
            actions = non_trade or actions
        if len(actions) == 1:
            self.last_explanation = {"kind": "forced", "note": _action_note(actions[0])}
            return actions[0]

        vps_to_win = getattr(game, "vps_to_win", 10)
        opp = enemy_strength(game.state, self.color, self.weights, vps_to_win)
        lam = self.trade.lam(opp)

        best_val = float("-inf")
        best = actions[0]
        for a in actions:
            g2 = game.copy()
            g2.execute(a)
            val = strength(g2.state, self.color, self.weights, vps_to_win)
            if a.action_type == ActionType.MARITIME_TRADE:
                # Only trade when it strictly improves the position (readiness),
                # scaled a touch by lambda so a leading opponent nudges us to
                # barter more; the tiny epsilon avoids trading on exact ties.
                val += 0.001 * lam - 0.002
            if val > best_val:
                best_val = val
                best = a

        if best.action_type == ActionType.MARITIME_TRADE:
            self.maritime_trades += 1
            self.last_explanation = {
                "kind": "trade",
                "note": "maritime",
                "reasoning": {
                    "lambda": round(lam, 3),
                    "net": round(best_val, 3),
                    "my_gain": round(best_val, 3),
                    "their_gain": 0.0,
                    "required": round(self.trade.margin, 3),
                    "vetoed": False,
                },
            }
        else:
            self.last_explanation = {
                "kind": "value",
                "note": f"{_action_note(best)} (strength {best_val:.2f})",
            }
        return best


def _action_note(action) -> str:
    t = action.action_type
    name = t.value if hasattr(t, "value") else str(t)
    return name.replace("_", " ").lower()
