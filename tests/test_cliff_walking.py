"""Cliff Walking: rewards, the cliff reset, the two classic routes."""

from __future__ import annotations

import pytest

from strategy_lab.core.match import play_out
from strategy_lab.games.cliff_walking import CliffWalking

#: Gymnasium numbers its actions UP, RIGHT, DOWN, LEFT.
GYM_ACTIONS = {0: "up", 1: "right", 2: "down", 3: "left"}


def walk(g, moves):
    s = g.initial_state()
    for m in moves:
        s = g.apply_action(s, m)
    return s


def test_every_step_costs_one_and_the_goal_ends_the_game():
    g = CliffWalking()
    s = walk(g, ["up"] + ["right"] * 11 + ["down"])
    assert g.is_terminal(s) and g.returns(s) == [-13.0]


def test_the_cliff_costs_100_and_returns_to_the_start():
    g = CliffWalking()
    s = walk(g, ["right"])                       # (3, 1) is the cliff
    assert s.pos == g.start and s.total == -100.0 and not g.is_terminal(s)
    assert walk(g, ["down"]).total == -1.0       # bumping the edge still costs 1


def test_model_equals_gymnasium_except_for_the_goal_cell():
    pytest.importorskip("gymnasium")
    from gymnasium.envs.toy_text.cliffwalking import CliffWalkingEnv
    env = CliffWalkingEnv()
    g = CliffWalking()
    for cell in range(48):
        if g.tile(cell) == "G":
            continue
        for a, move in GYM_ACTIONS.items():
            ours = {(nxt, r, done): p for p, nxt, r, done in g.model[cell][move]}
            theirs = {(int(nxt), float(r), bool(done)): p for p, nxt, r, done in env.P[cell][a]}
            assert ours == pytest.approx(theirs), (cell, move)


def test_slippery_variant_splits_a_move_three_ways():
    g = CliffWalking(slippery=True)
    assert len(g.slip_outcomes("up")) == 3 and g.stochastic


def test_optimal_return_is_the_shortest_path_when_nothing_slips():
    g = CliffWalking()
    plan = g.optimal(gamma=1.0)
    assert plan.values[g.start] == pytest.approx(-13.0)


def test_scripted_bots_walk_the_two_routes():
    g = CliffWalking()
    assert play_out(g, [g.make_policy("eddie")], 1)[0] == [-13.0]
    assert play_out(g, [g.make_policy("hana")], 1)[0] == [-17.0]
    assert play_out(g, [g.make_policy("vera")], 1)[0] == [-13.0]


def test_high_road_beats_the_edge_when_slipping():
    g = CliffWalking(slippery=True)
    from strategy_lab.core.match import simulate
    edge = simulate(g, [g.make_policy("eddie")], n=60, seed=1).mean_return(0)
    high = simulate(g, [g.make_policy("hana")], n=60, seed=1).mean_return(0)
    assert high > edge


def test_step_limit_default_and_challenge_scores():
    g = CliffWalking()
    assert g.step_limit == 150
    scores = {c.id: c.value for c in g.challenges if c.kind == "score"}
    assert scores == {"safe": -17, "shortest": -13}
