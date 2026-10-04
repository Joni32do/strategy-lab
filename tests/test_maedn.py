"""Mensch aergere dich nicht: board geometry, entering, captures, variants, cards, scene."""

from __future__ import annotations

import itertools
import json
import random

import pytest

from strategy_lab.core import CHANCE
from strategy_lab.core.match import play_out, simulate
from strategy_lab.games.maedn import (
    ARM_START, BASE_CELLS, ENTER, HOME_CELLS, RING_CELLS, Maedn, MaednState)


def state(g, tokens, turn=0, die=0, tries=1):
    """A decision state: ``tokens`` is a list of four-token lists (sorted for you)."""
    st = MaednState(tokens=[sorted(t) for t in tokens], turn=turn, to_move=turn, die=die)
    st.tries = tries
    return st


def two(mine, theirs, **kw):
    return state(None, [mine, theirs], **kw)


def decide(g, cards, s, seed=0):
    pol = g.make_policy(cards=cards)
    return pol.decide(g, s, s.turn, random.Random(seed))


B = -1


# ------------------------------------------------------------------- geometry
def adjacent(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def test_the_board_is_a_closed_ring_of_40_squares():
    assert len(set(RING_CELLS)) == 40
    assert all(0 <= r < 11 and 0 <= c < 11 for r, c in RING_CELLS)
    for i, cell in enumerate(RING_CELLS):
        assert adjacent(cell, RING_CELLS[(i + 1) % 40]), f"gap after ring square {i}"


def test_start_squares_home_rows_and_bases_fit_the_cross():
    ring = set(RING_CELLS)
    seen = set(ring)
    for arm in range(4):
        lane = HOME_CELLS[arm]
        tip = RING_CELLS[(ARM_START[arm] - 1) % 40]          # the square before the start
        assert adjacent(tip, lane[0]), f"arm {arm}: the home row must start next to the tip"
        assert all(adjacent(a, b) for a, b in zip(lane, lane[1:]))
        for cell in itertools.chain(lane, BASE_CELLS[arm]):
            assert cell not in seen, f"{cell} is used twice"
            seen.add(cell)
    assert len(seen) == 40 + 16 + 16
    assert RING_CELLS[ARM_START[0]] == (4, 0) and RING_CELLS[ARM_START[2]] == (6, 10)


def test_seats_take_arms_in_order_and_two_players_sit_opposite():
    assert Maedn(players=2).start == [0, 20]
    assert Maedn(players=3).start == [0, 10, 20]
    assert Maedn(players=4).start == [0, 10, 20, 30]
    assert Maedn().num_players == 4 and Maedn.meta()["players"] == 4
    with pytest.raises(ValueError):
        Maedn(players=5)


# ----------------------------------------------------------------- entering
def test_only_a_six_brings_a_token_out_and_not_onto_your_own_token():
    g = Maedn(players=2)
    s = two([B, B, B, B], [B, B, B, B], die=5)
    assert g.legal_actions(s) == []
    s = two([B, B, B, B], [B, B, B, B], die=6)
    assert g.legal_actions(s) == [ENTER]
    s = two([0, B, B, B], [B, B, B, B], die=6)              # own token on the start square
    assert g.legal_actions(s) == [0]                        # only that token can move
    s = two([0, 6, B, B], [B, B, B, B], die=6)              # ... and it is blocked by your own token
    assert g.legal_actions(s) == [6]


def test_entering_sets_a_token_on_the_start_square_and_rolls_again():
    g = Maedn(players=2)
    s = two([B, B, B, B], [B, B, B, B], die=6)
    s = g.apply_action(s, ENTER)
    assert s.tokens[0] == [B, B, B, 0]
    assert s.turn == 0 and g.current_player(s) == CHANCE      # a 6 gives another roll


def test_entering_captures_an_opponent_standing_on_your_start_square():
    g = Maedn(players=2)
    # seat 1 starts at ring square 20; its progress 20 is ring square 0 = seat 0's start
    s = two([B, B, B, B], [20, B, B, B], die=6)
    s = g.apply_action(s, ENTER)
    assert s.tokens[0] == [B, B, B, 0] and s.tokens[1] == [B, B, B, B]


def test_start_token_variant_begins_with_one_token_out():
    g = Maedn(players=2, start_token=True)
    s = g.initial_state()
    assert s.tokens == [[B, B, B, 0], [B, B, B, 0]]


# ------------------------------------------------------------------- moving
def test_moves_jump_over_tokens_but_not_onto_your_own():
    g = Maedn(players=2)
    s = two([3, 5, B, B], [B, B, B, B], die=2)
    assert g.legal_actions(s) == [5]                         # 3 + 2 lands on own token at 5
    s = two([3, 4, B, B], [B, B, B, B], die=2)
    assert g.legal_actions(s) == [3, 4]                      # jumping over the token at 4 is fine


def test_home_cells_need_an_exact_roll_and_can_be_jumped():
    g = Maedn(players=2)
    s = two([38, B, B, B], [B, B, B, B], die=5)
    assert g.legal_actions(s) == [38]                        # 38 + 5 = 43, the last home cell
    s = two([38, B, B, B], [B, B, B, B], die=6)
    assert 38 not in g.legal_actions(s)                      # 44 does not exist
    s = two([40, 42, B, B], [B, B, B, B], die=3)
    assert g.legal_actions(s) == [40]                        # 40 -> 43 jumps over 42
    s = two([40, 41, 43, B], [B, B, B, B], die=2)
    assert g.legal_actions(s) == [40]                        # 41 + 2 = 43 is taken, 40 + 2 = 42 is free
    s = two([39, 43, B, B], [B, B, B, B], die=4)
    assert g.legal_actions(s) == []                          # 39 + 4 = 43 is taken


def test_a_token_can_move_on_inside_the_home_cells():
    g = Maedn(players=2)
    s = two([40, B, B, B], [B, B, B, B], die=2)
    s = g.apply_action(s, 40)
    assert s.tokens[0] == [B, B, B, 42]


def test_landing_on_an_opponent_captures_it():
    g = Maedn(players=2)
    # my progress 5 + 4 = 9 is ring square 9; seat 1 progress 29 is ring square (20 + 29) % 40 = 9
    s = two([5, B, B, B], [29, B, B, B], die=4)
    s = g.apply_action(s, 5)
    assert s.tokens[0] == [B, B, B, 9] and s.tokens[1] == [B, B, B, B]


def test_tokens_in_a_home_row_cannot_be_captured():
    g = Maedn(players=2)
    s = two([36, B, B, B], [41, B, B, B], die=4)            # seat 1 sits on its home cell 2
    s = g.apply_action(s, 36)
    assert s.tokens[1] == [B, B, B, 41]


def test_turn_passes_after_a_move_but_a_six_rolls_again():
    g = Maedn(players=2)
    s = g.apply_action(two([5, B, B, B], [B, B, B, B], die=3), 5)
    assert s.turn == 1 and g.current_player(s) == CHANCE
    s = g.apply_action(two([5, B, B, B], [B, B, B, B], die=6), 5)
    assert s.turn == 0 and g.current_player(s) == CHANCE


def test_no_legal_move_passes_the_turn_without_an_extra_roll():
    g = Maedn(players=2)
    s = g.initial_state()
    s = g.apply_action(s, 4)                                 # all tokens in base, a 4
    assert s.turn == 1 and g.current_player(s) == CHANCE
    assert g.describe_chance(g.initial_state(), 4) == "rolls a 4: no move"
    assert g.describe_chance(g.initial_state(), 6) == "rolls a 6"


def test_a_six_that_cannot_move_does_not_grant_a_roll():
    g = Maedn(players=2)
    s = two([B, B, B, 43], [B, B, B, B], die=0)
    s.to_move = CHANCE
    # tokens [ -1, -1, -1, 43 ]: a 6 can bring one out, so it moves
    assert g.moves(s, 0, 6) == [ENTER]
    s = two([40, 41, 42, 43], [B, B, B, B], die=0)
    assert g.moves(s, 0, 6) == []


def test_winning_requires_all_four_tokens_home():
    g = Maedn(players=2)
    s = two([40, 41, 42, 39], [B, B, B, B], die=4)
    s = g.apply_action(s, 39)
    assert g.is_terminal(s) and g.winner(s) == 0
    assert g.returns(s) == [1.0, -1.0]
    g4 = Maedn(players=4)
    s = state(g4, [[40, 41, 42, 39], [B] * 4, [B] * 4, [B] * 4], die=4)
    s = g4.apply_action(s, 39)
    assert g4.returns(s) == [1.0, -1.0, -1.0, -1.0]


# ------------------------------------------------------------------ variants
def test_forced_entry_makes_a_six_bring_a_token_out_and_clears_the_start():
    g = Maedn(players=2, forced_entry=True)
    s = two([7, B, B, B], [B, B, B, B], die=6)
    assert g.legal_actions(s) == [ENTER]                     # must come out, not move 7
    s = two([0, 7, B, B], [B, B, B, B], die=3)
    assert g.legal_actions(s) == [0]                         # clear the start first
    s = two([0, 6, B, B], [B, B, B, B], die=6)               # the start token is blocked by 6
    assert g.legal_actions(s) == [6]
    s = two([0, 5, 6, 7], [B, B, B, B], die=3)               # nothing left in base: free choice
    assert set(g.legal_actions(s)) == {0, 5, 6, 7}
    assert set(Maedn(players=2).legal_actions(two([7, B, B, B], [B] * 4, die=6))) == {ENTER, 7}


def test_must_capture_limits_the_choice_to_capturing_moves():
    g = Maedn(players=2, must_capture=True)
    s = two([5, 12, B, B], [29, B, B, B], die=4)             # 5 + 4 captures at square 9
    assert g.legal_actions(s) == [5]
    s = two([5, 12, B, B], [B, B, B, B], die=4)              # nothing to capture: free choice
    assert set(g.legal_actions(s)) == {5, 12}
    assert set(Maedn(players=2).legal_actions(two([5, 12, B, B], [29, B, B, B], die=4))) == {5, 12}


def test_three_tries_for_a_six_when_nothing_is_on_the_track():
    g = Maedn(players=2, three_tries=True)
    s = g.initial_state()
    assert s.tries == 3
    s = g.apply_action(s, 2)
    assert s.turn == 0 and s.tries == 2 and g.current_player(s) == CHANCE
    s = g.apply_action(s, 3)
    assert s.turn == 0 and s.tries == 1
    s = g.apply_action(s, 5)                                 # third failure: the turn passes
    assert s.turn == 1 and s.tries == 3 and g.current_player(s) == CHANCE
    s = g.apply_action(g.initial_state(), 2)
    s = g.apply_action(s, 6)                                 # a six on the second try
    assert g.current_player(s) == 0 and g.legal_actions(s) == [ENTER]
    assert g.describe_chance(g.initial_state(), 2) == "rolls a 2: no move, tries again (2 left)"


def test_three_tries_only_when_no_token_is_on_the_track_or_can_still_advance_at_home():
    g = Maedn(players=2, three_tries=True)
    assert g._can_try_thrice(two([B, B, B, B], [B] * 4), 0)
    assert g._can_try_thrice(two([B, B, B, 43], [B] * 4), 0)       # packed at the end of the row
    assert g._can_try_thrice(two([B, B, 42, 43], [B] * 4), 0)
    assert not g._can_try_thrice(two([B, B, B, 42], [B] * 4), 0)   # could still move one cell
    assert not g._can_try_thrice(two([B, B, B, 5], [B] * 4), 0)    # a token on the track


def test_variants_are_off_by_default():
    p = Maedn().p
    assert not (p["three_tries"] or p["must_capture"] or p["forced_entry"] or p["start_token"])


# --------------------------------------------------------------------- cards
def test_fresh_legs_brings_a_token_out():
    g = Maedn(players=2)
    s = two([7, B, B, B], [B] * 4, die=6)
    assert decide(g, ["enter"], s)["action"] == ENTER
    assert decide(g, ["enter"], two([7, B, B, B], [B] * 4, die=3))["reason"] == "forced"


def test_headhunter_takes_the_furthest_victim():
    g = Maedn(players=2)
    # seat 1 tokens at progress 29 (ring 9) and 31 (ring 11); my tokens reach both with die 4
    s = two([5, 7, B, B], [29, 31, B, B], die=4)
    out = decide(g, ["hunt"], s)
    assert out["action"] == 7 and out["card"] == "hunt"          # captures progress 31 first
    assert decide(g, ["hunt"], two([5, 7, B, B], [B] * 4, die=4))["card"] is None


def test_safe_harbor_moves_into_the_home_cells():
    g = Maedn(players=2)
    s = two([37, 10, B, B], [B] * 4, die=4)
    assert decide(g, ["home"], s)["action"] == 37               # 37 + 4 = 41
    assert decide(g, ["home"], two([10, 12, B, B], [B] * 4, die=4))["card"] is None


def test_out_of_reach_avoids_stopping_in_front_of_an_enemy():
    g = Maedn(players=2)
    # enemy at ring square 8 (progress 28). My moves: 5 -> 9 (1 ahead of the enemy), 0 -> 4.
    s = two([5, 0, B, B], [28, B, B, B], die=4)
    out = decide(g, ["dodge"], s)
    assert out["action"] == 0 and out["vetoed"] == [("dodge", [5])]
    # home cells and squares behind the enemy are safe
    assert g.card_dodge(two([36, B, B, B], [28, B, B, B], die=5), 36, 0) is False


def test_front_runner_and_rear_guard_ignore_tokens_in_the_home_cells_and_the_base():
    g = Maedn(players=2)
    s = two([3, 10, 41, B], [B] * 4, die=2)
    assert decide(g, ["front"], s)["action"] == 10
    assert decide(g, ["rear"], s)["action"] == 3
    only_home = two([40, B, B, B], [B] * 4, die=1)
    assert decide(g, ["front"], only_home)["reason"] == "forced"


def test_clear_the_start_moves_the_token_on_the_start_square():
    g = Maedn(players=2)
    s = two([0, 9, B, B], [B] * 4, die=3)
    assert decide(g, ["clear-start"], s)["action"] == 0


def test_bots_and_cards_are_consistent():
    ids = {c.id for c in Maedn.cards()}
    assert ids == {"enter", "hunt", "home", "dodge", "front", "rear", "clear-start"}
    for b in Maedn().bots:
        assert set(b.cards) <= ids
    assert Maedn.lineage() == ["Game", "DiceGame", "RollAndMoveGame", "Maedn"]
    assert Maedn.family()["id"] == "roll-and-move"


# ---------------------------------------------------------------------- scene
def test_scene_board_is_the_cross_shaped_11_by_11_grid():
    g = Maedn(players=4)
    s = g.apply_action(g.apply_action(g.initial_state(), 6), ENTER)
    sc = g.scene(s, 0)
    json.dumps(sc)
    board = sc["parts"][0]
    cells = board["cells"]
    assert board["view"] == "grid" and board["rows"] == board["cols"] == 11 and len(cells) == 121
    assert sum(1 for c in cells if c is not None) == 40 + 16 + 16
    assert cells[0 * 11 + 2] is None and cells[2 * 11 + 2] is None      # off the cross
    # every seat's four base cells hold its four tokens (seat 0 has one out after the roll)
    base_pieces = [len(cells[r * 11 + c].get("pieces", [])) for r, c in BASE_CELLS[0]]
    assert sum(base_pieces) == 3
    # the start squares are marked in the seat colors
    assert cells[4 * 11 + 0]["tone"] == "p0" and cells[0 * 11 + 6]["tone"] == "p1"


def test_scene_marks_unused_arms_with_two_players():
    g = Maedn(players=2)
    cells = g.scene(g.initial_state(), 0)["parts"][0]["cells"]
    assert cells[HOME_CELLS[1][0][0] * 11 + HOME_CELLS[1][0][1]]["tone"] == "muted"
    assert cells[HOME_CELLS[2][0][0] * 11 + HOME_CELLS[2][0][1]]["tone"] == "p1"


def test_scene_puts_the_move_on_the_token_and_on_its_destination():
    g = Maedn(players=2)
    s = two([5, 12, B, B], [B] * 4, die=3)
    board = g.scene(s, 0)["parts"][0]["cells"]
    src5 = RING_CELLS[5]
    dst5 = RING_CELLS[8]
    assert board[src5[0] * 11 + src5[1]]["action"] == 5
    assert board[dst5[0] * 11 + dst5[1]]["action"] == 5
    assert board[RING_CELLS[12][0] * 11 + RING_CELLS[12][1]]["action"] == 12
    assert board[BASE_CELLS[0][0][0] * 11 + BASE_CELLS[0][0][1]].get("action") is None
    # six: entering is clickable on the base token and on the start square
    s = two([5, B, B, B], [B] * 4, die=6)
    board = g.scene(s, 0)["parts"][0]["cells"]
    assert board[BASE_CELLS[0][0][0] * 11 + BASE_CELLS[0][0][1]]["action"] == ENTER
    assert board[4 * 11 + 0]["action"] == ENTER
    # the other seat gets no clickable elements
    other = g.scene(s, 1)["parts"][0]["cells"]
    assert not any(c and "action" in c for c in other)


def test_scene_scoreboard_and_status():
    g = Maedn(players=2)
    s = two([40, 41, B, 5], [B] * 4, die=3)
    sc = g.scene(s, 0)
    assert sc["players"][0]["score"] == "2 of 4 home"
    assert sc["players"][0]["sub"] == "1 on the track, 1 in base"
    assert sc["status"] == "You rolled a 3: choose a token"
    one = two([40, 41, 43, 5], [B] * 4, die=3)
    assert g.status(one, 0) == "You rolled a 3: one legal move"
    assert g.status(s, 1) == "Player 1 rolled a 3 and is moving"
    assert sc["parts"][1]["view"] == "dice"


def test_captions():
    g = Maedn(players=2)
    s = two([5, B, B, B], [29, B, B, B], die=4)
    assert g.describe(s, 5, 0) == "moves a token 4 squares and kicks Player 2's token back to base"
    s = two([B, B, B, B], [B] * 4, die=6)
    assert g.describe(s, ENTER, 0) == "brings a token out and rolls again"
    s = two([38, B, B, B], [B] * 4, die=4)
    assert g.describe(s, 38, 0) == "moves a token 4 squares into the home cells"
    assert g.move_label(two([5, B, B, B], [29, B, B, B], die=4), 5) == \
        "Move from step 6 to step 10 and capture"


def test_standing_decides_a_timeout():
    g = Maedn(players=2)
    s = two([43, 42, 41, 40], [20, 21, B, B])
    assert g.timeout_returns(s) == [1.0, -1.0]


# ----------------------------------------------------------------- simulation
@pytest.mark.parametrize("players", [2, 3, 4])
def test_random_playouts_keep_the_board_consistent(players):
    g = Maedn(players=players, three_tries=True, must_capture=True, forced_entry=True)
    rng = random.Random(players)
    for _ in range(4):
        s = g.initial_state()
        while not g.is_terminal(s):
            for seat, toks in enumerate(s.tokens):
                assert toks == sorted(toks) and len(toks) == 4
                real = [q for q in toks if q != B]
                assert len(real) == len(set(real)), "two own tokens share a cell"
            squares = [g.square_of(seat, q) for seat, toks in enumerate(s.tokens) for q in toks]
            squares = [q for q in squares if q is not None]
            assert len(squares) == len(set(squares)), "two tokens share a ring square"
            if g.current_player(s) == CHANCE:
                a = g.sample_chance(s, rng)
            else:
                a = rng.choice(g.legal_actions(s))
            s = g.apply_action(s, a)
        assert g.winner(s) is not None


def test_games_end_without_timeouts_for_every_variant_mix():
    for flags in itertools.product([False, True], repeat=4):
        kw = dict(zip(("three_tries", "must_capture", "forced_entry", "start_token"), flags))
        g = Maedn(players=3, **kw)
        rets, steps, timeout = play_out(g, [g.make_policy("randy")] * 3, "variants")
        assert not timeout, kw


def win_rate(g, a, b, n, seed=1):
    res = simulate(g, [g.make_policy(a), g.make_policy(b)], n=n, seed=seed)
    return res.wins(0) / n


def test_capturing_stacks_beat_random_and_greta_beats_the_rest():
    g = Maedn(players=2)
    assert win_rate(g, "hugo", "randy", 200) > 0.6            # true rate about 0.69
    assert win_rate(g, "greta", "randy", 200) > 0.65          # about 0.74
    assert win_rate(g, "hugo", "sven", 200) > 0.58            # about 0.67
    assert 0.38 < win_rate(g, "greta", "hugo", 300) < 0.72    # about 0.55: a close game


def test_a_strong_bot_beats_three_random_seats_more_than_a_quarter_of_the_time():
    g = Maedn(players=4)
    res = simulate(g, [g.make_policy("greta"), g.make_policy("randy")], n=120, seed=4)
    assert res.wins(0) / 120 > 0.3                             # fair share would be 0.25


def test_insight_texts():
    g = Maedn()
    base = {"n": 100, "wins": [30, 70], "bot": "sven"}
    assert "Fresh legs" in g.insight({**base, "cards": ["front"]})
    assert "Strong showing" in g.insight({**base, "wins": [70, 30], "cards": ["enter"]})
    assert g.insight({**base, "wins": [45, 55], "cards": ["enter"]}) is None
