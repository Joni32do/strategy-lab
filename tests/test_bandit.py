"""The multi-armed bandit: hidden odds, chance nodes, bots, regret."""

from __future__ import annotations

import json
import random

import pytest

from strategy_lab.core import CHANCE, Seat, Session
from strategy_lab.core.match import simulate
from strategy_lab.games.bandit import Bandit, draw_probabilities, ucb1_index


def started(g, seed=123, pulls=()):
    """A state after the odds were drawn (from ``seed``) and some pulls with reward 1."""
    s = g.apply_action(g.initial_state(), seed)
    for arm, reward in pulls:
        s = g.apply_action(g.apply_action(s, arm), reward)
    return s


def test_odds_come_from_a_seed_chance_node():
    g = Bandit()
    s = g.initial_state()
    assert g.current_player(s) == CHANCE
    with pytest.raises(NotImplementedError):
        g.chance_outcomes(s)
    assert isinstance(g.sample_chance(s, random.Random(1)), int)
    a, b = started(g, 5), started(g, 5)
    assert a.probs == b.probs == draw_probabilities(5, 5)
    assert started(g, 6).probs != a.probs and len(a.probs) == 5


def test_each_pull_resolves_through_a_reward_chance_node():
    g = Bandit()
    s = g.apply_action(started(g, 9), 2)                     # pull arm C
    assert g.current_player(s) == CHANCE and s.pending == 2
    p = s.probs[2]
    assert dict(g.chance_outcomes(s)) == pytest.approx({0: 1 - p, 1: p})
    s = g.apply_action(s, 1)
    assert s.pulls[2] == 1 and s.wins[2] == 1 and s.total == 1 and g.current_player(s) == 0
    assert s.n == 1 and s.trail == [(2, 1)]


def test_game_ends_after_the_last_pull_and_win_means_over_half():
    g = Bandit(arms=2, pulls=5)
    s = started(g, 1, [(0, 1)] * 5)
    assert g.is_terminal(s) and g.returns(s) == [5.0]
    assert g.outcome([3.0], 0) == "win" and g.outcome([2.0], 0) == "loss"
    assert Bandit(pulls=6).outcome([3.0], 0) == "draw"


def test_the_seed_step_is_private_in_the_move_log():
    g = Bandit()
    sess = Session(g, [Seat("human")], 4)
    sess.advance()
    first = sess.steps[0]
    assert first.player == CHANCE and first.private == ()
    hidden = first.to_json(0, viewer=0)
    assert hidden["hidden"] is True and "a" not in hidden
    assert first.to_json(0, viewer=None)["a"] == first.action     # a spectator log keeps it


def test_scene_hides_the_odds_until_the_last_pull():
    g = Bandit(arms=3, pulls=5)
    mid = started(g, 7, [(0, 1)])
    text = json.dumps(g.scene(mid, 0))
    for p in mid.probs:
        assert f"{p:.2f}" not in text
    assert g.scene(mid, 0)["parts"][0]["arms"][0]["action"] == 0
    end = started(g, 7, [(0, 1), (1, 0), (2, 0), (0, 1), (0, 0)])
    assert f"{end.probs[0]:.2f}" in json.dumps(g.scene(end, 0))
    json.dumps(g.scene(g.initial_state(), 0))


def test_cards_and_bots_see_only_counts():
    g = Bandit()
    a, b = started(g, 1, [(0, 1), (1, 0)]), started(g, 2, [(0, 1), (1, 0)])
    assert g.observation(a, 0) == g.observation(b, 0)             # different odds, same view
    rng = random.Random(0)
    legal = g.legal_actions(a)
    assert g.card("untried").fn(g, a, legal, 0, rng) in (2, 3, 4)
    only_winner = started(g, 1, [(1, 1), (0, 0), (2, 0), (3, 0), (4, 0)])
    assert g.card("exploit").fn(g, only_winner, legal, 0, rng) == 1     # mean 1.0 beats 0.0
    assert g.card("untried").fn(g, only_winner, legal, 0, rng) is None  # nothing left to try


def test_ucb_index_prefers_unknown_arms_and_shrinks_with_pulls():
    assert ucb1_index(0.5, 0, 10) == float("inf")
    assert ucb1_index(0.5, 1, 10) > ucb1_index(0.5, 10, 10) > 0.5


def test_ucb_pulls_every_arm_first_then_the_best_looking():
    g = Bandit()
    s = started(g)
    ucb = g.make_policy("ursula")
    seen = set()
    for _ in range(5):
        a = ucb.act(g, s, 0, random.Random(len(seen)))
        seen.add(a)
        s = g.apply_action(g.apply_action(s, a), 0)
    assert seen == {0, 1, 2, 3, 4}


def test_explore_card_fires_about_one_pull_in_ten():
    g = Bandit()
    s = started(g)
    card = g.card("explore")
    rng = random.Random(0)
    hits = sum(card.fn(g, s, list(range(5)), 0, rng) is not None for _ in range(2000))
    assert 140 < hits < 260


def test_thoughtful_bots_beat_random_and_ucb_beats_greedy_over_many_games():
    g = Bandit(pulls=60)
    means = {b.id: simulate(g, [g.make_policy(b.id)], n=150, seed=3).mean_return(0)
             for b in g.bots}
    assert means["ursula"] > means["randy"] + 5
    assert means["cleo"] > means["randy"] + 5
    assert means["randy"] == pytest.approx(60 * 0.5, abs=3.0)
