"""Nim: rules, the nim-sum theory checked against the exact solver, symmetry, bots."""

from __future__ import annotations

import itertools
import json
import random

import pytest

from strategy_lab.core import Seat, Session, Solver
from strategy_lab.core.match import simulate
from strategy_lab.games.nim import Nim, nim_sum, parse_heaps, split


def play(g, actions):
    s = g.initial_state()
    for a in actions:
        s = g.apply_action(s, a)
    return s


def at(g, heaps, to_move=0):
    s = g.initial_state()
    s.heaps = list(heaps)
    s.to_move = to_move
    return s


def test_parse_heaps_accepts_lists_and_rejects_nonsense():
    assert parse_heaps("3,4,5") == [3, 4, 5]
    assert parse_heaps(" 1; 3 5 ") == [1, 3, 5]
    for bad in ("", "0,2", "a,b", "1," + ",".join(["2"] * 7), "16"):
        with pytest.raises(ValueError):
            parse_heaps(bad)
    with pytest.raises(ValueError):
        Nim(heaps="x")


def test_moves_and_normal_play_winner():
    g = Nim(heaps="2,1")
    assert sorted(g.legal_actions(g.initial_state())) == ["0:1", "0:2", "1:1"]
    assert split("1:3") == (1, 3)
    s = play(g, ["0:2", "1:1"])                         # player 1 takes the last object
    assert g.is_terminal(s) and g.winner(s) == 1 and g.returns(s) == [-1.0, 1.0]


def test_misere_reverses_the_winner():
    g = Nim(heaps="2,1", misere=True)
    s = play(g, ["0:2", "1:1"])
    assert g.winner(s) == 0


def test_nim_sum():
    assert nim_sum([3, 4, 5]) == 2 and nim_sum([1, 2, 3]) == 0 and nim_sum([]) == 0


@pytest.mark.parametrize("misere", [False, True])
def test_theory_matches_the_exact_solver_on_every_small_position(misere):
    g = Nim(heaps="1,1,1", misere=misere)
    solver = Solver(g)
    for sizes in itertools.product(range(0, 5), repeat=4):
        if not any(sizes):
            continue
        s = at(g, sizes)
        mover_wins = solver.value(s) > 0
        assert mover_wins == (not g.is_losing(list(sizes))), (sizes, misere)


@pytest.mark.parametrize("misere", [False, True])
def test_winning_moves_win_and_losing_positions_have_none(misere):
    g = Nim(heaps="1,1,1", misere=misere)
    solver = Solver(g)
    for sizes in itertools.product(range(0, 5), repeat=3):
        if not any(sizes):
            continue
        s = at(g, sizes)
        moves = g.winning_moves(s)
        assert bool(moves) == (not g.is_losing(list(sizes)))
        for a in moves:                                   # each leaves a lost position
            child = g.apply_action(s, a)
            if g.is_terminal(child):
                assert not misere and g.winner(child) == 0   # taking the last object wins
            else:
                assert solver.value(child) > 0           # player 0 wins: the opponent is lost
                assert g.is_losing(child.heaps)


def test_misere_endgame_leaves_an_odd_number_of_singles():
    g = Nim(heaps="3,1", misere=True)
    # one big heap and one single: reduce the big heap to 0, leaving one single
    assert g.winning_moves(at(g, [3, 1])) == ["0:3"]
    assert g.winning_moves(at(g, [1, 1])) == ["0:1", "1:1"]
    assert g.winning_moves(at(g, [1, 1, 1])) == []         # an odd number of singles is lost


def test_nimsum_card_plays_the_winning_move_and_nothing_when_lost():
    g = Nim()
    card = g.card("nimsum")
    s = g.initial_state()                                  # 3,4,5: nim-sum 2
    a = card.fn(g, s, g.legal_actions(s), 0, random.Random(0))
    assert nim_sum(g.apply_action(s, a).heaps) == 0
    lost = at(g, [1, 2, 3])
    assert card.fn(g, lost, g.legal_actions(lost), 0, random.Random(0)) is None


def test_card_behaviour():
    g = Nim()
    s = g.initial_state()
    rng = random.Random(0)
    assert g.card("biggest").fn(g, s, g.legal_actions(s), 0, rng) == "2:5"
    assert split(g.card("one").fn(g, s, g.legal_actions(s), 0, rng))[1] == 1
    even = g.card("even").fn(g, s, g.legal_actions(s), 0, rng)
    after = g.apply_action(s, even).heaps
    assert len(set(after)) < len(after)                    # two heaps now match


def test_symmetry_sorts_heaps_and_groups_moves_on_equal_heaps():
    g = Nim()
    a, b = at(g, [3, 4, 5]), at(g, [5, 3, 4])
    assert g.key(a) != g.key(b) and g.canonical_key(a) == g.canonical_key(b)
    s = at(g, [3, 3, 5])
    classes = g.action_classes(s, g.legal_actions(s))
    assert len(g.legal_actions(s)) == 11 and len(classes) == 8
    assert ["0:1", "1:1"] in classes
    assert all(g.canonical_key(g.apply_action(s, m[0])) == g.canonical_key(g.apply_action(s, m[1]))
               for m in classes if len(m) == 2)


def test_scene_offers_a_take_action_per_count():
    g = Nim()
    scene = g.scene(g.initial_state(), 0)
    part = scene["parts"][0]
    assert part["view"] == "heaps"
    assert part["heaps"][1]["count"] == 4 and part["heaps"][1]["actions"] == [
        "1:1", "1:2", "1:3", "1:4"]
    json.dumps(scene)
    done = g.scene(play(g, ["0:3", "1:4", "2:5"]), 0)["parts"][0]
    assert all("actions" not in h for h in done["heaps"])


def test_nina_never_loses_from_a_winning_position_and_beats_everyone_there():
    g = Nim()                                              # nim-sum 2: the mover wins
    nina = g.make_policy("nina")
    for bot in ("randy", "toby", "bea", "nina"):
        res = simulate(g, [nina, g.make_policy(bot)], n=60, seed=5)
        first = res.to_json()["firstMover"][0]
        assert first["wins"] == first["games"], f"Nina lost as first mover against {bot}"


def test_nimsum_stack_scores_half_against_nina_and_sweeps_the_weak_bots():
    g = Nim()
    stack = g.make_policy(cards=["nimsum", "one"])
    assert simulate(g, [stack, g.make_policy("nina")], n=100, seed=1).wins(0) == 50
    for bot in ("randy", "toby", "bea"):
        assert simulate(g, [stack, g.make_policy(bot)], n=60, seed=1).wins(0) == 60


def test_session_replays_and_status_texts():
    g = Nim()
    sess = Session(g, [Seat("human"), Seat("bot", "nina")], 1)
    sess.advance()
    sess.act("0:1")
    sess.advance()
    again = Session(g, sess.seats, 1, sess.log, strict=True)
    assert g.key(again.state) == g.key(sess.state)
    assert "Your move" in g.status(sess.state, 0)
    assert "loses" in Nim(misere=True).status(Nim(misere=True).initial_state(), 0)
