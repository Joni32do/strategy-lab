"""Sanity tests for the trading policy. Run: uv run python server/test_policy.py"""
import random

from catanatron.game import Game
from catanatron.models.player import RandomPlayer, Color
from catanatron.players.value import ValueFunctionPlayer
from catanatron.models.enums import ActionType, ActionPrompt
from catanatron.state_functions import player_has_rolled, get_player_freqdeck

from policy import (
    StrategicTradingPlayer,
    MetricWeights,
    TradeParams,
    position_strength,
    trade_coefficient,
    evaluate_trade,
)


def test_coefficient_is_nonlinear_and_monotone():
    tp = TradeParams()
    xs = [i / 20 for i in range(21)]
    ys = [trade_coefficient(x, tp) for x in xs]
    assert all(b >= a - 1e-9 for a, b in zip(ys, ys[1:])), "lambda must be monotone"
    assert ys[0] < 0.2 * tp.lam_max, "weak opponent -> near zero"
    assert ys[-1] > 0.8 * tp.lam_max, "strong opponent -> near lam_max"
    # non-linear: slope around the midpoint is far steeper than at the tails
    mid_slope = ys[11] - ys[9]
    tail_slope = ys[1] - ys[0]
    assert mid_slope > 5 * tail_slope, "should be S-shaped, not linear"
    print("ok  coefficient non-linear & monotone:", [round(y, 2) for y in ys[::4]])


def test_metric_symmetry():
    random.seed(7)
    g = Game([ValueFunctionPlayer(Color.RED), ValueFunctionPlayer(Color.BLUE)])
    for _ in range(120):
        if g.winning_color() is not None:
            break
        g.play_tick()
    w = MetricWeights()
    sr, _ = position_strength(g, Color.RED, w)
    sb, _ = position_strength(g, Color.BLUE, w)
    assert 0.0 <= sr <= 1.0 and 0.0 <= sb <= 1.0
    # same function applied to each color: leader by VP must not be weaker
    vr = g.state.player_state["P0_VICTORY_POINTS"]
    vb = g.state.player_state["P1_VICTORY_POINTS"]
    if vr != vb:
        assert (sr > sb) == (vr > vb), "strength must track VP ordering"
    print(f"ok  metric symmetric: RED s={sr:.2f}(vp{vr}) BLUE s={sb:.2f}(vp{vb})")


def test_leader_veto():
    """A near-winning opponent must be refused even on a self-beneficial swap."""
    random.seed(2)
    g = Game([RandomPlayer(Color.RED), RandomPlayer(Color.BLUE)])
    tp = TradeParams(veto_vp_margin=1)
    w = MetricWeights()
    # force BLUE to 9 VP (vps_to_win=10 -> within margin)
    g.state.player_state["P1_VICTORY_POINTS"] = 9
    g.state.player_state["P1_ACTUAL_VICTORY_POINTS"] = 9
    give = [1, 0, 0, 0, 0]  # give wood
    get = [0, 0, 0, 0, 1]   # get ore
    ok, info = evaluate_trade(g, Color.RED, Color.BLUE, give, get, w, tp)
    assert info["vetoed"] is True and ok is False, info
    print("ok  leader veto blocks the trade:", info["opp_vp"], "VP opponent")


def test_trade_actually_happens_in_a_game():
    """Two trading players should produce at least some confirmed trades."""
    confirmed = 0
    for seed in range(8):
        random.seed(seed)
        p0 = StrategicTradingPlayer(Color.RED, trade_params=TradeParams(margin=0.0))
        p1 = StrategicTradingPlayer(Color.BLUE, trade_params=TradeParams(margin=0.0))
        g = Game([p0, p1])
        g.play()
        confirmed += p0.stats["confirms"] + p1.stats["confirms"]
    assert confirmed > 0, "expected at least one confirmed trade across 8 games"
    print(f"ok  trades occur in real games: {confirmed} confirmed across 8 games")


def test_offer_round_trip():
    """An OFFER_TRADE from the player drives the engine into DECIDE_TRADE."""
    random.seed(5)
    p0 = StrategicTradingPlayer(Color.RED, trade_params=TradeParams(margin=0.0))
    g = Game([p0, RandomPlayer(Color.BLUE)])
    saw_offer = False
    for _ in range(400):
        if g.winning_color() is not None:
            break
        before = g.state.current_prompt
        rec = g.play_tick()
        if rec.action.action_type == ActionType.OFFER_TRADE:
            saw_offer = True
            assert g.state.current_prompt == ActionPrompt.DECIDE_TRADE
    print(f"ok  offer round-trip (saw_offer={saw_offer}, offers={p0.stats['offers']})")


def test_blocking_preference_changes_builds():
    """block_weight > 0 should make the VALUE brain pick blocking builds sometimes,
    and it must never override a winning move (games still finish normally)."""
    plain = blocked = 0
    for seed in range(12):
        random.seed(seed)
        b = StrategicTradingPlayer(Color.RED, weights=MetricWeights(block_weight=2.0))
        Game([b, ValueFunctionPlayer(Color.BLUE)]).play()
        blocked += b.stats["blocks"]

        random.seed(seed)
        p = StrategicTradingPlayer(Color.RED, weights=MetricWeights(block_weight=0.0))
        Game([p, ValueFunctionPlayer(Color.BLUE)]).play()
        plain += p.stats["blocks"]
    assert plain == 0, "block_weight=0 must never register a blocking build"
    assert blocked > 0, "block_weight>0 should produce blocking builds"
    print(f"ok  blocking preference: {blocked} blocking builds w/ knob up, {plain} with it off")


def test_alphabeta_base_bot_plays():
    """The selectable ALPHABETA base brain should drive a full game without error."""
    from policy import AlphaBetaPlayer
    if AlphaBetaPlayer is None:
        print("skip  alphabeta base bot (AlphaBetaPlayer unavailable)")
        return
    random.seed(1)
    you = StrategicTradingPlayer(Color.RED, base_bot="ALPHABETA")
    assert you.base_bot == "ALPHABETA" and not you._base_is_value
    g = Game([you, RandomPlayer(Color.BLUE)])
    for _ in range(300):
        if g.winning_color() is not None:
            break
        g.play_tick()
    print("ok  alphabeta base bot drives a game")


if __name__ == "__main__":
    test_coefficient_is_nonlinear_and_monotone()
    test_metric_symmetry()
    test_leader_veto()
    test_offer_round_trip()
    test_trade_actually_happens_in_a_game()
    test_blocking_preference_changes_builds()
    test_alphabeta_base_bot_plays()
    print("\nALL PASSED")
