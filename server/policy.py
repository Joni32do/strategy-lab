"""
A state-dependent trading policy for Catanatron.

Nothing here re-implements Catan rules: the engine (catanatron) owns all of
that. This module only adds *strategy* on top of it:

  1. position_strength(game, color) -> a scalar in [0, 1] estimating how close
     a player is to winning. It is the same function for every color (a
     relabelling symmetry), so equivalent positions map to equivalent
     behaviour regardless of seat.

  2. A trade valuation in "resource-equivalent" units, again symmetric across
     colors, so a trade is judged by *relative* gains rather than by who holds
     which cards.

  3. A non-linear "trade coefficient" lambda(opponent_strength): how heavily we
     count the *opponent's* benefit against our own. Near zero when the
     opponent is weak (pure self-interest); large when they lead; and a hard
     veto once they are within `veto_vp_margin` of victory -- you never hand a
     resource to someone about to win.

The acceptance rule is the single line that ties it together:

    net = my_gain - lambda(opp_strength) * their_gain
    accept  <=>  net >= margin + premium_per_vp * max(0, opp_vp - my_vp)

The `premium_per_vp` term is the user's worked example made literal: if the
trade partner is 2 VP ahead, you demand ~1 extra resource of value before you
will deal.

The player itself delegates every non-trade decision to Catanatron's
ValueFunctionPlayer, so the only new "brain" is the trading logic.
"""

from dataclasses import dataclass, asdict, field
import math

from catanatron.models.player import Player
from catanatron.models.enums import Action, ActionType, ActionPrompt, RESOURCES
from catanatron.state_functions import (
    get_actual_victory_points,
    get_player_freqdeck,
    get_longest_road_length,
    player_has_rolled,
)
from catanatron.features import build_production_features
from catanatron.models.decks import (
    ROAD_COST_FREQDECK,
    SETTLEMENT_COST_FREQDECK,
    CITY_COST_FREQDECK,
    DEVELOPMENT_CARD_COST_FREQDECK,
)
from catanatron.players.value import ValueFunctionPlayer, base_fn, DEFAULT_WEIGHTS

try:
    from catanatron.players.minimax import AlphaBetaPlayer
except Exception:  # optional / heavier
    AlphaBetaPlayer = None

# Blocking scores are measured in "opponent expansion nodes denied". This unit
# puts one denied node on the same scale as catanatron's *production* value term
# (~1e8 per pip), so block_weight reads as "denying an opponent node is worth this
# many production-equivalents". Small block_weight only flips near-ties; large
# block_weight sacrifices real economy to block -- but VP-level value (~1e14) always
# wins, so a blocking preference never throws away a winning move.
BLOCK_UNIT = 1e8

# freqdeck index order, fixed by catanatron: [WOOD, BRICK, SHEEP, WHEAT, ORE]
N_RES = len(RESOURCES)
_PRODUCTION = build_production_features(True)  # consider_robber=True

# Build targets in priority order; value of a resource rises when it completes
# (or moves you toward) a build you cannot yet afford.
TARGETS = [
    ("CITY", CITY_COST_FREQDECK, 5.0),
    ("SETTLEMENT", SETTLEMENT_COST_FREQDECK, 4.0),
    ("DEV_CARD", DEVELOPMENT_CARD_COST_FREQDECK, 2.0),
    ("ROAD", ROAD_COST_FREQDECK, 1.0),
]


# --------------------------------------------------------------------------- #
# Tunable parameters (exposed to the UI tuner)
# --------------------------------------------------------------------------- #
@dataclass
class MetricWeights:
    """Weights for the position-strength metric. vp dominates on purpose:
    closeness-to-victory is what 'strength' should mostly mean."""

    vp: float = 0.6
    production: float = 0.25
    expansion: float = 0.15
    prod_norm: float = 12.0  # total pips that count as a 'full' economy
    expansion_norm: float = 8.0  # buildable nodes that count as 'full' reach
    block_weight: float = 0.0  # how much to prefer builds that deny an opponent
    #                            expansion nodes ("build a road/settlement to block").
    #                            0 = pure value function; higher = block harder.

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(**{k: float(d[k]) for k in d if k in cls.__dataclass_fields__})


@dataclass
class TradeParams:
    """Shape of the non-linear trade coefficient and the acceptance threshold."""

    lam_max: float = 2.5  # ceiling of lambda(opp_strength)
    lam_steepness: float = 8.0  # how sharply lambda turns on around the midpoint
    lam_midpoint: float = 0.5  # opponent strength at which lambda = lam_max/2
    veto_vp_margin: int = 1  # never trade if opp within this many VP of winning
    margin: float = 0.15  # min net value (resource units) to bother trading
    premium_per_vp: float = 0.5  # extra value demanded per VP the opp is ahead
    scarcity_weight: float = 1.0  # value of a resource you barely produce
    need_weight: float = 1.5  # value of a resource that completes a build
    base_value: float = 0.5  # floor value of any resource

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        out = {}
        for k in d:
            if k in cls.__dataclass_fields__:
                out[k] = int(d[k]) if k == "veto_vp_margin" else float(d[k])
        return cls(**out)


# --------------------------------------------------------------------------- #
# The derived metric: position strength
# --------------------------------------------------------------------------- #
def production_vector(game, color):
    """Expected per-resource production (pips) for `color`, robber-aware."""
    sample = _PRODUCTION(game, color)
    return [sample[f"EFFECTIVE_P0_{r}_PRODUCTION"] for r in RESOURCES]


def position_strength(game, color, weights: MetricWeights):
    """Scalar in [0, 1] estimating how close `color` is to winning.

    Same function for every color -> the symmetry that makes similar positions
    elicit similar behaviour. Returns (strength, breakdown) for the UI.
    """
    state = game.state
    vp = get_actual_victory_points(state, color)
    vp_term = min(vp / max(game.vps_to_win, 1), 1.0)

    prod = sum(production_vector(game, color))
    prod_term = min(prod / weights.prod_norm, 1.0) if weights.prod_norm else 0.0

    buildable = len(state.board.buildable_node_ids(color))
    exp_term = (
        min(buildable / weights.expansion_norm, 1.0) if weights.expansion_norm else 0.0
    )

    strength = (
        weights.vp * vp_term
        + weights.production * prod_term
        + weights.expansion * exp_term
    )
    strength = max(0.0, min(1.0, strength))
    breakdown = {
        "strength": strength,
        "vp": vp,
        "vp_term": vp_term,
        "production": prod,
        "prod_term": prod_term,
        "buildable": buildable,
        "exp_term": exp_term,
    }
    return strength, breakdown


# --------------------------------------------------------------------------- #
# Trade valuation (resource-equivalent units), symmetric across colors
# --------------------------------------------------------------------------- #
def resource_values(game, color, tp: TradeParams):
    """Marginal value to `color` of *receiving* one of each resource.

    value = base + scarcity(you barely produce it) + need(it completes a build).
    """
    hand = get_player_freqdeck(game.state, color)
    prod = production_vector(game, color)
    peak = max(prod) or 1.0

    values = []
    for i in range(N_RES):
        scarcity = 1.0 - (prod[i] / peak)  # 1 = you make none, 0 = your best
        need = 0.0
        for _name, cost, prio in TARGETS:
            missing = [max(cost[k] - hand[k], 0) for k in range(N_RES)]
            total_missing = sum(missing)
            if total_missing == 0:
                continue  # already affordable; this target adds no pull
            if missing[i] > 0:
                # closer to done (smaller total_missing) -> stronger pull
                need = max(need, prio / total_missing)
        values.append(
            tp.base_value + tp.scarcity_weight * scarcity + tp.need_weight * need
        )
    return values


def hand_gain(game, color, give, get, tp: TradeParams):
    """Value to `color` of giving `give` and receiving `get` (freqdecks)."""
    v = resource_values(game, color, tp)
    return sum(get[i] * v[i] for i in range(N_RES)) - sum(
        give[i] * v[i] for i in range(N_RES)
    )


def trade_coefficient(opp_strength, tp: TradeParams):
    """lambda(opp_strength): logistic ramp from ~0 to lam_max.

    Weak opponent -> ~0 (act in pure self-interest).
    Strong opponent -> lam_max (their gain counts heavily against the deal).
    """
    z = tp.lam_steepness * (opp_strength - tp.lam_midpoint)
    # guard against overflow for extreme steepness
    z = max(-60.0, min(60.0, z))
    return tp.lam_max / (1.0 + math.exp(-z))


def evaluate_trade(game, me, opp, give, get, weights, tp):
    """Decide whether `me` should do a trade (give -> opp, get <- opp).

    Returns (ok: bool, info: dict) where info explains the decision for the UI.
    """
    my_vp = get_actual_victory_points(game.state, me)
    opp_vp = get_actual_victory_points(game.state, opp)
    opp_strength, _ = position_strength(game, opp, weights)

    # Hard veto: never feed a player on the cusp of winning.
    vetoed = opp_vp >= game.vps_to_win - tp.veto_vp_margin

    my_gain = hand_gain(game, me, give, get, tp)
    # opponent's view of the same swap: they give `get`, receive `give`.
    their_gain = hand_gain(game, opp, get, give, tp)

    lam = trade_coefficient(opp_strength, tp)
    net = my_gain - lam * their_gain
    required = tp.margin + tp.premium_per_vp * max(0, opp_vp - my_vp)
    ok = (not vetoed) and (my_gain > 0) and (net >= required)

    info = {
        "ok": ok,
        "vetoed": vetoed,
        "my_vp": my_vp,
        "opp_vp": opp_vp,
        "opp_strength": round(opp_strength, 3),
        "lambda": round(lam, 3),
        "my_gain": round(my_gain, 3),
        "their_gain": round(their_gain, 3),
        "net": round(net, 3),
        "required": round(required, 3),
    }
    return ok, info


# --------------------------------------------------------------------------- #
# The player
# --------------------------------------------------------------------------- #
def _candidate_offers(hand, opp_hand, needed):
    """Bounded set of (give, get) single-resource swaps worth considering.

    give: 1 or 2 of a resource we hold; get: 1 of a resource we need and the
    opponent actually holds (so they *can* accept). Keeps the offer space tiny.
    """
    offers = []
    for gi in range(N_RES):
        if hand[gi] <= 0:
            continue
        for ai in range(N_RES):
            if ai == gi or opp_hand[ai] <= 0 or needed[ai] <= 0:
                continue
            give = [0] * N_RES
            get = [0] * N_RES
            give[gi] = 1
            get[ai] = 1
            offers.append((tuple(give), tuple(get)))
            if hand[gi] >= 2:  # a 2-for-1 sweetener we can afford
                give2 = [0] * N_RES
                give2[gi] = 2
                offers.append((tuple(give2), tuple(get)))
    return offers


def _needed_vector(hand):
    """1 for resources that are still missing for some build target, else 0."""
    needed = [0] * N_RES
    for _name, cost, _prio in TARGETS:
        for i in range(N_RES):
            if cost[i] - hand[i] > 0:
                needed[i] = 1
    return needed


def _can_afford_priority_build(hand):
    """True if a settlement or city is already affordable (don't trade then)."""
    for cost in (SETTLEMENT_COST_FREQDECK, CITY_COST_FREQDECK):
        if all(hand[i] >= cost[i] for i in range(N_RES)):
            return True
    return False


class StrategicTradingPlayer(Player):
    """ValueFunctionPlayer for everything except trades, plus a state-dependent
    trading brain driven by `position_strength` and the non-linear coefficient.

    Set is_bot=True so the engine treats it as automated.
    """

    def __init__(
        self,
        color,
        weights: MetricWeights = None,
        trade_params: TradeParams = None,
        enable_trade: bool = True,
        base_bot: str = "VALUE",
        is_bot: bool = True,
    ):
        super().__init__(color, is_bot)
        self.weights = weights or MetricWeights()
        self.tp = trade_params or TradeParams()
        self.enable_trade = enable_trade
        self.base_bot = (base_bot or "VALUE").upper()
        if self.base_bot == "ALPHABETA" and AlphaBetaPlayer is not None:
            self._base = AlphaBetaPlayer(color, 2, True)
            self._base_is_value = False
        else:
            self.base_bot = "VALUE"
            self._base = ValueFunctionPlayer(color)
            self._base_is_value = True
        # Same heuristic ValueFunctionPlayer scores with; reused so the blocking
        # re-ranking stays commensurate with the base bot's own preferences.
        self._value_fn = base_fn(DEFAULT_WEIGHTS)
        self._last_offer_turn = -1
        self.last_explanation = None
        self.stats = {
            "offers": 0,
            "accepts": 0,
            "rejects": 0,
            "confirms": 0,
            "cancels": 0,
            "vetoes": 0,
            "blocks": 0,
        }

    # -- helpers ----------------------------------------------------------- #
    def _opponent_colors(self, game):
        return [c for c in game.state.colors if c != self.color]

    def _base_decision(self, game, playable_actions, note="value-function best move"):
        action = self._base.decide(game, playable_actions)
        self.last_explanation = {"kind": "play", "note": note, "action": _action_str(action)}
        return action

    # -- main -------------------------------------------------------------- #
    def decide(self, game, playable_actions):
        if len(playable_actions) == 1:
            self.last_explanation = {
                "kind": "forced",
                "note": "only one legal action",
                "action": _action_str(playable_actions[0]),
            }
            return playable_actions[0]

        prompt = game.state.current_prompt

        if prompt == ActionPrompt.DECIDE_TRADE:
            return self._decide_on_offer(game, playable_actions)
        if prompt == ActionPrompt.DECIDE_ACCEPTEES:
            return self._decide_acceptee(game, playable_actions)
        if (
            self.enable_trade
            and prompt == ActionPrompt.PLAY_TURN
            and player_has_rolled(game.state, self.color)
            and not game.state.is_resolving_trade
        ):
            offer = self._maybe_offer(game)
            if offer is not None:
                return offer

        return self._play_decision(game, playable_actions)

    # -- choosing a build/play, with an optional blocking preference --------- #
    def _play_decision(self, game, playable_actions):
        """Delegate to the base bot, unless blocking is enabled: then re-rank the
        base heuristic value by a bonus for builds that deny opponents expansion
        nodes. Only meaningful with the VALUE base (ALPHABETA runs its own search).
        """
        bw = getattr(self.weights, "block_weight", 0.0)
        if bw <= 0 or not self._base_is_value:
            return self._base_decision(game, playable_actions)

        opps = self._opponent_colors(game)
        before = sum(len(game.state.board.buildable_node_ids(o)) for o in opps)

        best, best_score, best_block = None, float("-inf"), 0.0
        for action in playable_actions:
            game_copy = game.copy()
            try:
                game_copy.execute(action)
            except Exception:
                continue
            value = self._value_fn(game_copy, self.color)
            block = 0.0
            if action.action_type in (ActionType.BUILD_SETTLEMENT, ActionType.BUILD_ROAD):
                after = sum(len(game_copy.state.board.buildable_node_ids(o)) for o in opps)
                block = float(before - after)  # nodes we removed from their reach
            score = value + bw * BLOCK_UNIT * block
            if score > best_score:
                best, best_score, best_block = action, score, block

        if best is None:
            return self._base_decision(game, playable_actions)

        if best_block > 0:
            self.stats["blocks"] += 1
            note = f"blocking build (denies {int(best_block)} opp node{'s' if best_block != 1 else ''})"
        else:
            note = "value-function best move"
        self.last_explanation = {"kind": "play", "note": note, "action": _action_str(best)}
        return best

    # -- responding to someone else's offer -------------------------------- #
    def _decide_on_offer(self, game, playable_actions):
        trade = game.state.current_trade
        offering = list(trade[0:N_RES])  # what offerer gives -> we receive
        asking = list(trade[N_RES : 2 * N_RES])  # what offerer wants -> we give
        offerer = game.state.colors[trade[2 * N_RES]]

        # Engine quirk: when the offerer isn't seated first, catanatron re-asks
        # the *offerer* about its own pending offer. You can't respond to your
        # own offer, so just reject to let resolution continue (to the acceptee
        # phase if anyone accepted, otherwise back to play).
        if offerer == self.color:
            self.last_explanation = {"kind": "own-offer", "note": "engine re-asked offerer; passing"}
            return next(a for a in playable_actions if a.action_type == ActionType.REJECT_TRADE)

        can_accept = any(a.action_type == ActionType.ACCEPT_TRADE for a in playable_actions)
        # From our seat: give `asking`, get `offering`.
        ok, info = evaluate_trade(
            game, self.color, offerer, asking, offering, self.weights, self.tp
        )
        accept = can_accept and ok
        self.last_explanation = {
            "kind": "respond",
            "note": "accept" if accept else ("can't afford" if not can_accept else "decline"),
            "trade": {"give": asking, "get": offering, "with": offerer.value},
            "reasoning": info,
        }
        if accept:
            self.stats["accepts"] += 1
            return next(a for a in playable_actions if a.action_type == ActionType.ACCEPT_TRADE)
        if info["vetoed"]:
            self.stats["vetoes"] += 1
        self.stats["rejects"] += 1
        return next(a for a in playable_actions if a.action_type == ActionType.REJECT_TRADE)

    # -- choosing whom to confirm with, as the offerer --------------------- #
    def _decide_acceptee(self, game, playable_actions):
        trade = game.state.current_trade
        offering = list(trade[0:N_RES])  # we give
        asking = list(trade[N_RES : 2 * N_RES])  # we get
        confirms = [a for a in playable_actions if a.action_type == ActionType.CONFIRM_TRADE]

        best, best_net, best_info = None, None, None
        for a in confirms:
            other = a.value[2 * N_RES]
            ok, info = evaluate_trade(
                game, self.color, other, offering, asking, self.weights, self.tp
            )
            if ok and (best_net is None or info["net"] > best_net):
                best, best_net, best_info = a, info["net"], info

        if best is not None:
            self.stats["confirms"] += 1
            self.last_explanation = {
                "kind": "confirm",
                "note": f"confirm with {best.value[2 * N_RES].value}",
                "trade": {"give": offering, "get": asking, "with": best.value[2 * N_RES].value},
                "reasoning": best_info,
            }
            return best

        self.stats["cancels"] += 1
        self.last_explanation = {"kind": "cancel", "note": "no acceptee worth it"}
        return next(a for a in playable_actions if a.action_type == ActionType.CANCEL_TRADE)

    # -- initiating an offer ----------------------------------------------- #
    def _maybe_offer(self, game):
        if self._last_offer_turn == game.state.num_turns:
            return None  # at most one offer attempt per turn (avoids loops)

        hand = get_player_freqdeck(game.state, self.color)
        if _can_afford_priority_build(hand):
            return None  # we can already build something good; don't trade away cards

        needed = _needed_vector(hand)
        if sum(needed) == 0:
            return None

        best, best_net, best_info, best_opp = None, None, None, None
        for opp in self._opponent_colors(game):
            opp_hand = get_player_freqdeck(game.state, opp)
            for give, get in _candidate_offers(hand, opp_hand, needed):
                ok, info = evaluate_trade(
                    game, self.color, opp, list(give), list(get), self.weights, self.tp
                )
                # require the deal to be plausibly acceptable to a rational opp
                if ok and info["their_gain"] > 0:
                    if best_net is None or info["net"] > best_net:
                        best, best_net, best_info, best_opp = (give, get), info["net"], info, opp

        if best is None:
            return None

        self._last_offer_turn = game.state.num_turns
        self.stats["offers"] += 1
        give, get = best
        self.last_explanation = {
            "kind": "offer",
            "note": f"offer to {best_opp.value}",
            "trade": {"give": list(give), "get": list(get), "with": best_opp.value},
            "reasoning": best_info,
        }
        # OFFER_TRADE value = (give x5, get x5); engine appends the offerer index.
        return Action(self.color, ActionType.OFFER_TRADE, (*give, *get))

    def reset_state(self):
        self._last_offer_turn = -1
        self.last_explanation = None


def _action_str(action):
    val = action.value
    return {"type": action.action_type.name, "by": action.color.value, "value": _jsonable(val)}


def _jsonable(v):
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if hasattr(v, "value"):  # enum-like
        try:
            return v.value
        except Exception:
            return str(v)
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)
