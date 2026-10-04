"""The Nash lens: equilibria, dominance, your habits, regret matching."""

from __future__ import annotations

import json
import math
import time

import pytest

from strategy_lab.core import Seat, Session
from strategy_lab.games.matching_pennies import MatchingPennies
from strategy_lab.games.nim import Nim
from strategy_lab.games.prisoners_dilemma import PrisonersDilemma
from strategy_lab.games.rps import RockPaperScissors
from strategy_lab.games.stag_hunt import StagHunt
from strategy_lab.lenses import all_lenses
from strategy_lab.lenses.nash import NashLens, dominance, regret_matching

lens = NashLens()


def session(g, my_moves=(), bot="nina", seed=2):
    """A human in seat 0 who plays ``my_moves`` against ``bot``."""
    sess = Session(g, [Seat("human"), Seat("bot", bot)], seed)
    sess.advance()
    for a in my_moves:
        sess.act(a)
        sess.advance()
    return sess


def test_registered_and_applies_only_to_matrix_games():
    assert "nash" in all_lenses()
    for cls in (RockPaperScissors, MatchingPennies, PrisonersDilemma, StagHunt):
        assert lens.applies(cls())
    assert not lens.applies(Nim())


def test_rps_mixed_equilibrium_is_one_third_each():
    r = lens.run(session(RockPaperScissors()), {})
    assert r["zeroSum"] and r["pure"] == []
    assert len(r["equilibria"]) == 1
    eq = r["equilibria"][0]
    assert eq["row"] == pytest.approx([1 / 3] * 3, abs=1e-3) and eq["col"] == eq["row"]
    assert eq["payoffs"] == [0.0, 0.0] and not eq["pure"]
    assert r["dominance"]["survivors"] == [[0, 1, 2], [0, 1, 2]]
    json.dumps(r)


def test_prisoners_dilemma_has_one_pure_equilibrium_and_a_dominant_strategy():
    r = lens.run(session(PrisonersDilemma()), {})
    assert [p["labels"] for p in r["pure"]] == [["Defect", "Defect"]]
    assert r["pure"][0]["payoffs"] == [1.0, 1.0]
    assert len(r["equilibria"]) == 1 and r["equilibria"][0]["pure"]
    assert r["dominance"]["dominant"] == [1, 1]
    assert r["dominance"]["dominated"][0] == [{"action": 0, "by": 1}]
    assert r["dominance"]["survivors"] == [[1], [1]] and not r["zeroSum"]


def test_stag_hunt_has_two_pure_equilibria_and_a_mixed_one():
    r = lens.run(session(StagHunt()), {})
    assert sorted(p["cell"] for p in r["pure"]) == [[0, 0], [1, 1]]
    assert len(r["equilibria"]) == 3
    mixed = [e for e in r["equilibria"] if not e["pure"]][0]
    assert mixed["row"] == pytest.approx([0.75, 0.25]) and mixed["method"] == "closed form"
    assert mixed["payoffs"] == [3.0, 3.0]
    assert r["dominance"]["dominant"] == [None, None]


def test_matching_pennies_has_no_pure_equilibrium():
    r = lens.run(session(MatchingPennies()), {})
    assert r["pure"] == [] and r["equilibria"][0]["row"] == [0.5, 0.5]


def test_your_habits_entropy_exploitability_and_best_response():
    g = RockPaperScissors()
    r = lens.run(session(g, [0] * 6, bot="rocky"), {})          # you throw rock, so does Rocky
    you = r["you"]
    assert r["rounds"] == 6 and r["empirical"]["freq"] == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert you["entropy"] == 0.0 and you["maxEntropy"] == pytest.approx(math.log2(3), abs=1e-3)
    assert you["predictability"] == 1.0
    assert you["exploitability"] == pytest.approx(1.0)          # a hunter wins 1 a round
    assert you["bestResponse"] == [1] and you["bestResponseLabels"] == ["Paper"]
    assert you["expected"] == [0.0, 1.0, -1.0]
    assert r["overlay"]["actions"]["1"] == {"text": "+1.00", "tone": "best", "value": 1.0}
    assert r["overlay"]["actions"]["2"]["tone"] == "bad"


def test_a_balanced_player_has_maximum_entropy_and_no_exploitability():
    g = RockPaperScissors()
    r = lens.run(session(g, [0, 1, 2] * 4, bot="nina"), {})
    you = r["you"]
    assert you["entropy"] == pytest.approx(math.log2(3), abs=1e-3)
    assert you["exploitability"] == pytest.approx(0.0, abs=1e-3)


def test_before_any_round_there_is_nothing_empirical():
    r = lens.run(session(RockPaperScissors()), {})
    assert r["you"] is None and r["overlay"] == {"actions": {}}
    assert r["empirical"]["freq"] == [None, None] and r["rounds"] == 0


def test_you_is_the_human_seat_even_in_seat_one():
    g = PrisonersDilemma()
    sess = Session(g, [Seat("bot", "carl"), Seat("human")], 1)
    sess.advance()
    sess.act(1)
    sess.advance()
    r = lens.run(sess, {})
    assert r["me"] == 1 and r["you"]["seat"] == 1 and r["you"]["freq"] == [0.0, 1.0]
    assert r["you"]["bestResponseLabels"] == ["Defect"]


def test_regret_matching_average_strategies_converge_to_nash_in_zero_sum_games():
    g = RockPaperScissors()
    points = regret_matching(g.A, g.B, 4000)
    assert points[0]["t"] == 1 and points[-1]["t"] == 4000
    assert points[0]["gap"] > 0.5 and points[-1]["gap"] < 0.05
    assert points[-1]["row"] == pytest.approx([1 / 3] * 3, abs=0.03)
    assert points[-1]["col"] == pytest.approx([1 / 3] * 3, abs=0.03)
    assert [p["t"] for p in points] == sorted(p["t"] for p in points)


def test_regret_matching_removes_a_dominated_action():
    g = PrisonersDilemma()
    last = regret_matching(g.A, g.B, 1000)[-1]
    assert last["row"][1] > 0.99 and last["col"][1] > 0.99


def test_iterations_option_and_runtime():
    start = time.perf_counter()
    r = lens.run(session(RockPaperScissors()), {})
    assert time.perf_counter() - start < 0.5
    assert r["regret"]["iterations"] == 500
    short = lens.run(session(RockPaperScissors()), {"iterations": 50})
    assert short["regret"]["points"][-1]["t"] == 50
    assert r["regret"]["equilibrium"]["row"] == pytest.approx([1 / 3] * 3, abs=1e-3)


def test_dominance_function_finds_dominance_and_survivors():
    d = dominance(PrisonersDilemma())
    assert d["dominant"] == [1, 1] and d["survivors"] == [[1], [1]]
