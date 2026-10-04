"""Matching Pennies: roles, the fair-coin equilibrium, the hunter."""

from __future__ import annotations

import random

import numpy as np

from strategy_lab.core.match import simulate
from strategy_lab.games.matching_pennies import HEADS, TAILS, MatchingPennies


def test_matcher_wins_when_coins_agree():
    g = MatchingPennies(rounds=1)
    assert g.payoff_table[HEADS][HEADS] == (1, -1)
    assert g.payoff_table[HEADS][TAILS] == (-1, 1)
    assert g.seat_label(0) == "Matcher" and g.seat_label(1) == "Mismatcher"


def test_no_pure_equilibrium_and_a_fair_coin_mix():
    g = MatchingPennies()
    assert [e for e in g.equilibria if e.pure] == []
    assert np.allclose(g.equilibrium_mix(0), 0.5) and np.allclose(g.equilibrium_mix(1), 0.5)


def test_flip_card_plays_the_opposite():
    g = MatchingPennies()
    s = g.apply_action(g.apply_action(g.initial_state(), HEADS), HEADS)
    flip = g.card("flip")
    assert flip.fn(g, s, [HEADS, TAILS], 0, random.Random(0)) == TAILS


def test_hunter_beats_a_player_who_always_shows_heads():
    g = MatchingPennies()
    res = simulate(g, [g.make_policy("hank"), g.make_policy("harry")], n=40, seed=1)
    assert res.mean_return(0) > 10


def test_the_fair_coin_scores_zero_on_average():
    g = MatchingPennies()
    res = simulate(g, [g.make_policy("nell"), g.make_policy("hank")], n=300, seed=3)
    assert abs(res.mean_return(0)) < 1.0
