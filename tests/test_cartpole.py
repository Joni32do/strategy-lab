"""CartPole and the GymGame adapter: seeded replay, rewards, the card ladder."""

from __future__ import annotations

import json
import random

from strategy_lab.core import CHANCE, Seat, Session
from strategy_lab.core.match import simulate
from strategy_lab.families.external import SEED_LIMIT, GymGame
from strategy_lab.games.cartpole import CartPole


def test_family_and_first_node_is_a_seed_chance_node():
    g = CartPole()
    assert isinstance(g, GymGame) and g.family()["id"] == "gymnasium"
    s = g.initial_state()
    assert g.current_player(s) == CHANCE
    try:
        g.chance_outcomes(s)
        raise AssertionError("the seed must not be enumerable")
    except NotImplementedError:
        pass
    seed = g.sample_chance(s, random.Random(1))
    assert 0 <= seed < SEED_LIMIT
    assert g.sample_chance(s, random.Random(1)) == seed


def test_same_seed_and_actions_give_the_same_episode():
    g = CartPole()
    a, b = g.initial_state(), g.initial_state()
    for s_ in (a, b):
        g.move(s_, 12345)
        for act in (0, 1, 1, 0, 1):
            g.move(s_, act)
    assert g.key(a) == g.key(b) and g.obs_vector(a) == g.obs_vector(b)
    other = g.initial_state()
    g.move(other, 999)
    assert g.obs_vector(other) != g.obs_vector(g.apply_action(g.initial_state(), 12345))


def test_copy_does_not_share_the_environment():
    g = CartPole()
    s = g.apply_action(g.initial_state(), 7)
    t = g.apply_action(s, 1)
    assert len(s.actions) == 0 and len(t.actions) == 1
    u = g.apply_action(s, 1)
    assert g.obs_vector(t) == g.obs_vector(u)           # branching from s is repeatable


def test_reward_is_one_per_step_and_returns_are_cumulative():
    g = CartPole()
    sess = Session(g, [Seat("bot", "random")], 3)
    while not sess.terminal:
        sess.step()
    steps = len(sess.state.actions)
    assert sess.returns() == [float(steps)]
    assert g.returns(sess.state) == [sess.state.total]


def test_session_replay_roundtrips_through_json():
    g = CartPole()
    sess = Session(g, [Seat("bot", "pete")], 4)
    for _ in range(40):
        sess.step()
    log = json.loads(json.dumps(sess.log))
    again = Session(g, sess.seats, 4, log, strict=True)
    assert g.key(again.state) == g.key(sess.state)


def test_scene_parts_and_labels():
    g = CartPole()
    sess = Session(g, [Seat("bot", "pete")], 4)
    for _ in range(10):
        sess.step()
    parts = g.scene(sess.state, 0)["parts"]
    pole = parts[0]
    assert pole["view"] == "cartpole"
    assert set(pole) >= {"x", "theta", "xLimit", "thetaLimit", "steps", "done"}
    assert pole["xLimit"] == 2.4 and pole["done"] is False
    assert parts[1]["view"] == "bars" and len(parts[1]["items"]) == 4
    assert [c["action"] for c in parts[2]["choices"]] == [0, 1]
    assert g.action_label(sess.state, 0) == "left" and g.action_label(sess.state, 1) == "right"
    assert "pushes the cart left" in g.describe(sess.state, 0, 0)


def test_card_ladder_orders_the_policies():
    g = CartPole()
    mean = {b.id: simulate(g, [g.make_policy(b.id)], n=15, seed=1).mean_return(0)
            for b in g.bots}
    assert mean["randy"] < mean["lee"] < mean["sue"] < mean["pete"]
    assert mean["pete"] > 450


def test_episode_cap_is_500_steps():
    g = CartPole()
    res = simulate(g, [g.make_policy("pete")], n=5, seed=2)
    assert max(r.returns[0] for r in res.games) <= 500
