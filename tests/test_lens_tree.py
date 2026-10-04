"""The tree lens: exact values, symmetry classes, heuristic fallback, size estimate."""

from __future__ import annotations

import json
import time

from strategy_lab.core import Seat, Session
from strategy_lab.games.connect_four import ConnectFour
from strategy_lab.games.matching_pennies import MatchingPennies
from strategy_lab.games.nim import Nim
from strategy_lab.games.tictactoe import TicTacToe
from strategy_lab.lenses import all_lenses, lenses_for
from strategy_lab.lenses.tree import TreeLens, estimate_size

lens = TreeLens()


def session(g, log=()):
    return Session(g, [Seat("human"), Seat("bot")], 0, list(log))


def test_registered_and_applies_only_to_deterministic_open_two_player_games():
    assert "tree" in all_lenses()
    assert lens.applies(TicTacToe()) and lens.applies(Nim()) and lens.applies(ConnectFour())
    assert not lens.applies(MatchingPennies())
    assert "tree" in [l.id for l in lenses_for(Nim())]
    assert "tree" not in [l.id for l in lenses_for(MatchingPennies())]


def test_tictactoe_root_is_a_draw_with_three_opening_classes():
    r = lens.run(session(TicTacToe()), {})
    assert r["mode"] == "exact" and r["text"] == "Draw" and r["outcome"] == "draw"
    assert r["symmetry"]["moves"] == 9 and r["symmetry"]["decisions"] == 3
    assert sorted(len(c["members"]) for c in r["symmetry"]["classes"]) == [1, 4, 4]
    assert all(a["text"] == "Draw" for a in r["actions"])
    assert len(r["tree"]["children"]) == 3
    assert len(r["best"]) == 9
    json.dumps(r)


def test_tictactoe_punishes_a_blunder():
    g = TicTacToe()
    r = lens.run(session(g, [{"p": 0, "a": 0}, {"p": 1, "a": 1}]), {})   # X corner, O edge
    values = {a["a"]: a["text"] for a in r["actions"]}
    assert values[4] == "Win"                       # the center wins against that reply
    assert r["text"] == "Win" and 4 in r["best"]
    assert r["overlay"]["actions"]["4"]["tone"] == "best"
    assert r["overlay"]["actions"]["4"]["text"] == "Win"


def test_nim_positions_with_zero_nim_sum_are_losses_for_the_mover():
    g = Nim(heaps="1,2,3")
    r = lens.run(session(g), {})
    assert r["mode"] == "exact" and r["text"] == "Loss" and r["outcome"] == "loss"
    assert all(a["text"] == "Loss" for a in r["actions"])
    assert r["moverName"] == "Player 1"


def test_nim_winning_position_has_exactly_the_nim_sum_moves():
    g = Nim()
    r = lens.run(session(g), {})
    assert r["text"] == "Win"
    assert set(r["best"]) == set(g.winning_moves(g.initial_state()))
    assert r["symmetry"]["decisions"] == 12
    assert r["pv"] and r["stats"]["distinct"] > 0 and r["stats"]["searched"] > 0


def test_values_are_from_the_movers_point_of_view():
    g = Nim()
    s = Session(g, [Seat("human"), Seat("bot")], 0, [{"p": 0, "a": "0:3"}])
    r = lens.run(s, {})                                   # player 1 to move on 0,4,5 (nim-sum 1)
    assert r["mover"] == 1 and r["text"] == "Win"


def test_symmetric_nim_moves_are_one_decision():
    g = Nim(heaps="3,3,5")
    r = lens.run(session(g), {})
    assert r["symmetry"]["moves"] == 11 and r["symmetry"]["decisions"] == 8


def test_connect_four_falls_back_to_heuristic_search():
    start = time.perf_counter()
    r = lens.run(session(ConnectFour()), {})
    assert time.perf_counter() - start < 1.0
    assert r["mode"] == "heuristic" and r["stats"]["depth"] == 4
    assert r["stats"]["distinct"] is None and r["stats"]["searched"] > 100
    assert r["symmetry"]["moves"] == 7 and r["symmetry"]["decisions"] == 4
    assert all(a["text"].startswith(("+", "-")) for a in r["actions"])
    assert 3 in r["best"]                                       # the middle column
    assert len(r["pv"]) == 4
    child = r["tree"]["children"][0]
    assert child["children"] and len(child["children"]) <= lens.preview_replies


def test_depth_option_changes_the_horizon():
    r = lens.run(session(ConnectFour()), {"depth": 2})
    assert r["stats"]["depth"] == 2 and len(r["pv"]) == 2


def test_small_budget_forces_the_fallback_on_a_game_that_normally_solves():
    r = lens.run(session(TicTacToe()), {"budget": 100})
    assert r["mode"] == "heuristic"


def test_too_big_without_a_heuristic_reports_an_estimate():
    g = Nim(heaps="15,15,15,15,15,15,15")
    r = lens.run(session(g), {})
    assert r["mode"] == "estimate" and r["tooBig"] and r["text"] == "too big"
    assert r["estimate"]["branching"] > 10 and r["estimate"]["log10Size"] > 15
    assert r["actions"] == [] and r["overlay"] == {"actions": {}}
    assert r["symmetry"]["decisions"] < r["symmetry"]["moves"]


def test_estimate_size_scales_with_the_game():
    small = estimate_size(TicTacToe(), TicTacToe().initial_state())
    big = estimate_size(ConnectFour(), ConnectFour().initial_state())
    assert small["log10Size"] < 8 < big["log10Size"]


def test_finished_game_has_nothing_to_analyze():
    g = Nim(heaps="1")
    s = Session(g, [Seat("human"), Seat("bot")], 0, [{"p": 0, "a": "0:1"}])
    r = lens.run(s, {})
    assert r["mode"] == "terminal" and r["actions"] == [] and r["tree"] is None


def test_lens_is_pure_and_deterministic():
    g = TicTacToe()
    s = session(g)
    before = g.key(s.state)
    a, b = lens.run(s, {}), lens.run(s, {})
    a["stats"].pop("seconds"), b["stats"].pop("seconds")
    assert a == b and g.key(s.state) == before
