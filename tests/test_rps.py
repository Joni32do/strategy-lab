"""Rock-Paper-Scissors: the table, the equilibrium, the bots."""

from __future__ import annotations

import numpy as np

from strategy_lab.core.match import simulate
from strategy_lab.games.rps import PAPER, ROCK, SCISSORS, RockPaperScissors, beats


def test_beats_and_payoffs():
    g = RockPaperScissors()
    assert beats(PAPER, ROCK) and beats(SCISSORS, PAPER) and beats(ROCK, SCISSORS)
    assert g.payoff_table[PAPER][ROCK] == (1, -1)
    assert g.payoff_table[ROCK][PAPER] == (-1, 1)
    assert g.payoff_table[SCISSORS][SCISSORS] == (0, 0)
    assert np.allclose(g.A + g.B, 0)                 # zero-sum


def test_the_only_equilibrium_is_one_third_each():
    g = RockPaperScissors()
    assert len(g.equilibria) == 1
    assert np.allclose(g.equilibrium_mix(0), 1 / 3) and np.allclose(g.equilibrium_mix(1), 1 / 3)


def test_log_caption_names_the_winning_move():
    g = RockPaperScissors()
    s = g.apply_action(g.initial_state(), ROCK)
    assert g.describe(s, PAPER, 1) == "plays Paper vs Rock: Paper beats Rock (+1)"
    assert g.describe(s, ROCK, 1).endswith("tie")


def test_rocky_is_exploited_and_nina_is_not():
    g = RockPaperScissors()
    hank, rocky, nina = (g.make_policy(b) for b in ("hank", "rocky", "nina"))
    assert simulate(g, [hank, rocky], n=30, seed=1).mean_return(0) > 10
    assert abs(simulate(g, [nina, rocky], n=300, seed=1).mean_return(0)) < 1.0


def test_cycle_card_walks_rock_paper_scissors():
    g = RockPaperScissors()
    s = g.initial_state()
    cycle = g.make_policy(cards=["cycle"])
    import random
    seen = []
    for _ in range(4):
        a = cycle.act(g, s, 0, random.Random(0))
        seen.append(a)
        s = g.apply_action(g.apply_action(s, a), 0)
    assert seen == [ROCK, PAPER, SCISSORS, ROCK]
