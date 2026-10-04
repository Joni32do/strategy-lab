"""Prisoner's Dilemma: payoffs, dominance, the classic partners."""

from __future__ import annotations

import numpy as np

from strategy_lab.core import Seat, Session
from strategy_lab.core.match import simulate
from strategy_lab.games.prisoners_dilemma import COOPERATE, DEFECT, P, R, S, T, PrisonersDilemma


def run(g, a, b, seed=1):
    """Return of policy ``a`` against policy ``b`` (``a`` sits in seat 0)."""
    from strategy_lab.core.match import play_out
    rets, _, _ = play_out(g, [g.make_policy(a), g.make_policy(b)], seed)
    return rets


def test_axelrod_payoffs():
    g = PrisonersDilemma()
    assert (T, R, P, S) == (5, 3, 1, 0) and T > R > P > S and 2 * R > T + S
    assert g.payoff_table[COOPERATE][COOPERATE] == (3, 3)
    assert g.payoff_table[DEFECT][COOPERATE] == (5, 0)
    assert g.payoff_table[COOPERATE][DEFECT] == (0, 5)
    assert g.payoff_table[DEFECT][DEFECT] == (1, 1)


def test_defect_defect_is_the_unique_equilibrium_and_dominant():
    g = PrisonersDilemma()
    assert [(e.row, e.col) for e in g.equilibria] == [((0.0, 1.0), (0.0, 1.0))]
    assert np.all(g.utility_matrix(0)[DEFECT] > g.utility_matrix(0)[COOPERATE])
    assert np.all(g.utility_matrix(1)[DEFECT] > g.utility_matrix(1)[COOPERATE])


def test_steady_cooperators_beat_steady_defectors_in_total():
    g = PrisonersDilemma(rounds=10)
    assert run(g, "pat", "pat") == [30, 30]
    assert run(g, "carl", "carl") == [10, 10]
    assert run(g, "carl", "pat") == [50, 0]


def test_tit_for_tat_opens_friendly_and_copies():
    g = PrisonersDilemma(rounds=10)
    assert run(g, "tess", "pat") == [30, 30]
    # against Always Defect it is the sucker once, then defects back
    assert run(g, "tess", "carl") == [S + 9 * P, T + 9 * P]


def test_grim_trigger_never_forgives():
    g = PrisonersDilemma(rounds=6)
    grim = g.card("grim")
    import random
    s = g.initial_state()
    for a, b in [(0, 0), (0, 1), (0, 0), (0, 0)]:      # they defected once, then cooperated
        s = g.apply_action(g.apply_action(s, a), b)
    assert grim.fn(g, s, [0, 1], 0, random.Random(0)) == DEFECT
    assert grim.fn(g, g.initial_state(), [0, 1], 0, random.Random(0)) == COOPERATE


def test_finale_card_defects_only_in_the_last_round():
    g = PrisonersDilemma(rounds=3)
    import random
    s = g.initial_state()
    fin = g.card("finale")
    for _ in range(2):
        assert fin.fn(g, s, [0, 1], 0, random.Random(0)) is None
        s = g.apply_action(g.apply_action(s, 0), 0)
    assert fin.fn(g, s, [0, 1], 0, random.Random(0)) == DEFECT


def test_defector_never_loses_a_pairing_but_cooperators_earn_more():
    g = PrisonersDilemma(rounds=10)
    res = simulate(g, [g.make_policy("carl"), g.make_policy("tess")], n=20, seed=1)
    assert res.wins(1) == 0 and res.wins(0) == 20
    assert res.mean_return(0) < run(g, "tess", "tess")[0]


def test_insight_mentions_the_cooperation_ceiling():
    g = PrisonersDilemma(rounds=10)
    sess = Session(g, [Seat("bot", "tess"), Seat("bot", "pat")], 0)
    sess.advance()
    assert g.insight({"bot": "tess", "meanReturns": [20.0, 25.0]}).count("30") == 1
