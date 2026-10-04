"""Stag Hunt: two pure equilibria and a mixed one."""

from __future__ import annotations

import numpy as np

from strategy_lab.core.match import play_out, simulate
from strategy_lab.games.stag_hunt import HARE, STAG, StagHunt


def test_inequalities_of_the_general_form():
    g = StagHunt()
    a, c = g.payoff_table[STAG][STAG][0], g.payoff_table[STAG][HARE][0]
    b, d = g.payoff_table[HARE][STAG][0], g.payoff_table[HARE][HARE][0]
    assert a > b >= d > c


def test_two_pure_equilibria_and_the_three_quarter_mix():
    g = StagHunt()
    pure = sorted((e.row, e.col) for e in g.equilibria if e.pure)
    assert pure == [((0.0, 1.0), (0.0, 1.0)), ((1.0, 0.0), (1.0, 0.0))]
    mixed = [e for e in g.equilibria if not e.pure]
    assert len(mixed) == 1 and np.allclose(mixed[0].row, [0.75, 0.25])
    assert g.reference_equilibrium() == mixed[0]


def test_hare_is_safe_and_stag_pays_only_together():
    g = StagHunt(rounds=10)
    hana, sam = g.make_policy("hana"), g.make_policy("sam")
    assert play_out(g, [hana, sam], 1)[0] == [30.0, 0.0]
    assert play_out(g, [sam, sam], 1)[0] == [40.0, 40.0]


def test_mixed_equilibrium_makes_the_other_side_indifferent():
    """Against the 3/4 mix, always-stag and always-hare both average 3 a round."""
    g = StagHunt(rounds=10)
    max_ = g.make_policy("max")
    res = simulate(g, [g.make_policy("sam"), max_], n=300, seed=2)
    assert 27 < res.mean_return(0) < 33
    res = simulate(g, [g.make_policy("hana"), max_], n=300, seed=2)
    assert res.mean_return(0) == 30.0                 # hare always pays 3


def test_copycat_cy_coordinates_on_stag_with_sam():
    g = StagHunt(rounds=10)
    assert play_out(g, [g.make_policy("cy"), g.make_policy("sam")], 1)[0] == [40.0, 40.0]
