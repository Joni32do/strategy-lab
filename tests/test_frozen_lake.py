"""FrozenLake: maps, slip odds and the transition model, checked against Gymnasium."""

from __future__ import annotations

import pytest

from strategy_lab.core import Seat, Session
from strategy_lab.core.match import simulate
from strategy_lab.games.frozen_lake import FrozenLake

#: Gymnasium numbers its actions LEFT, DOWN, RIGHT, UP.
GYM_ACTIONS = {0: "left", 1: "down", 2: "right", 3: "up"}


def merged(rows):
    """``[(p, next, reward, done)]`` -> ``{(next, reward, done): p}``."""
    out = {}
    for p, nxt, reward, done in rows:
        key = (int(nxt), float(reward), bool(done))
        out[key] = out.get(key, 0.0) + p
    return out


@pytest.mark.parametrize("size,slippery", [("4x4", True), ("4x4", False), ("8x8", True)])
def test_model_equals_gymnasiums_transition_table(size, slippery):
    pytest.importorskip("gymnasium")
    from gymnasium.envs.toy_text.frozen_lake import FrozenLakeEnv
    env = FrozenLakeEnv(map_name=size, is_slippery=slippery)
    g = FrozenLake(size=size, slippery=slippery)
    assert (g.rows, g.cols) == (env.nrow, env.ncol)
    for cell in range(env.nrow * env.ncol):
        for a, move in GYM_ACTIONS.items():
            assert merged(g.model[cell][move]) == pytest.approx(merged(env.P[cell][a])), \
                (cell, move)


def test_slip_odds_are_one_third_each():
    g = FrozenLake()
    assert dict(g.slip_outcomes("up")) == pytest.approx({"left": 1 / 3, "up": 1 / 3,
                                                         "right": 1 / 3})
    assert dict(FrozenLake(slippery=False).slip_outcomes("up")) == {"up": 1.0}


def test_maps_have_one_start_and_one_goal():
    for size, n in (("4x4", 4), ("8x8", 8)):
        g = FrozenLake(size=size)
        assert g.rows == g.cols == n and g.tile(0) == "S" and g.tile(n * n - 1) == "G"


def test_value_iteration_finds_the_known_optimum_of_the_slippery_lake():
    g = FrozenLake()
    plan = g.optimal(gamma=1.0)
    assert plan.values[0] == pytest.approx(0.8235, abs=1e-3)       # best chance to reach G


def test_greedy_policy_is_clearly_better_than_random_by_simulation():
    g = FrozenLake()
    plan = g.make_policy(cards=["plan"])
    res = simulate(g, [plan], n=300, seed=7)
    rand = simulate(g, [g.make_policy("randy")], n=300, seed=7)
    wins = sum(1 for r in res.games if r.returns[0] == 1.0)
    random_wins = sum(1 for r in rand.games if r.returns[0] == 1.0)
    assert wins / 300 > 0.55 and random_wins / 300 < 0.1


def test_dry_lake_is_solved_by_the_goal_card():
    g = FrozenLake(slippery=False)
    res = simulate(g, [g.make_policy("cleo")], n=20, seed=1)
    assert all(r.returns[0] == 1.0 for r in res.games)
    assert res.games[0].steps == 6                                  # shortest path on 4x4


def test_session_with_human_seat_resolves_slips_automatically():
    g = FrozenLake()
    sess = Session(g, [Seat("human")], 3)
    sess.advance()
    sess.act("right")
    sess.advance()
    assert sess.waiting_for_human() or sess.terminal
    assert len(sess.steps) == 2 and sess.steps[1].chance["prob"] == pytest.approx(1 / 3)
