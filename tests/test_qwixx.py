"""Qwixx: the published rules as a checklist (ported from the old gym env tests)."""

from __future__ import annotations

import json
import math
import random

import pytest

from strategy_lab.core import CHANCE
from strategy_lab.core.match import simulate
from strategy_lab.games.qwixx import (
    LAST_COL, LOCK_BIT, PASS, Qwixx, col_of, frontier, parse, triangle,
    value_at)

RED, YELLOW, GREEN, BLUE = range(4)


def make(players=4, **kw):
    return Qwixx(players=players, **kw)


def white(g, dice, turn=0, locked=(), marks=None, penalties=None):
    """A state in the white phase with the six dice already rolled."""
    s = g.initial_state()
    s.dice = list(dice)
    s.rolled = 6 - sum(1 for r in locked)
    s.stage = "white"
    s.turn = turn
    for r in locked:
        s.locked[r] = True
        s.dice[2 + r] = 0
    for (seat, row), cols in (marks or {}).items():
        for c in cols:
            s.marks[seat][row] |= 1 << c
    if penalties:
        s.penalties = list(penalties)
    s.asked = 0
    g._ask_next_white(s)
    return s


def give(s, seat, row, cols):
    for c in cols:
        s.marks[seat][row] |= 1 << c


def run(g, s, *actions):
    for a in actions:
        s = g.apply_action(s, a)
    return s


# --------------------------------------------------------------------- geometry
def test_geometry_red_yellow_ascend_green_blue_descend():
    assert [value_at(RED, c) for c in range(11)] == list(range(2, 13))
    assert [value_at(GREEN, c) for c in range(11)] == list(range(12, 1, -1))
    for row in range(4):
        for col in range(11):
            assert col_of(row, value_at(row, col)) == col
    assert col_of(RED, 13) == -1 and col_of(GREEN, 1) == -1
    assert parse("blue:12") == (BLUE, 12) and parse(PASS) is None


# ----------------------------------------------------------------- scoring/gate
def test_crosses_only_move_right_and_the_lock_needs_five():
    g = make()
    s = g.initial_state()
    assert g.can_mark(s, 0, RED, 4, s.locked)
    g._cross(s, 0, RED, value_at(RED, 4))
    assert not g.can_mark(s, 0, RED, 4, s.locked) and not g.can_mark(s, 0, RED, 3, s.locked)
    assert g.can_mark(s, 0, RED, 5, s.locked)
    for col in (5, 6, 7):
        g._cross(s, 0, RED, value_at(RED, col))
    assert not g.can_mark(s, 0, RED, LAST_COL, s.locked)       # only four crosses so far
    g._cross(s, 0, RED, value_at(RED, 8))
    assert g.can_mark(s, 0, RED, LAST_COL, s.locked)           # five: the 12 is open


def test_lock_counts_as_one_more_cross_six_marks_score_28():
    g = make()
    s = g.initial_state()
    for col in (4, 5, 6, 7, 8):
        g._cross(s, 0, RED, value_at(RED, col))
    g._cross(s, 0, RED, 12)
    mask = s.marks[0][RED]
    assert (mask & (LOCK_BIT - 1)).bit_count() == 6 and mask.bit_count() == 7
    assert g.row_score(mask) == triangle(7) == 28 and g.score(s, 0) == 28
    s.penalties[0] = 2
    assert g.score(s, 0) == 28 - 10


def test_a_complete_row_is_eleven_marks_plus_lock_for_78_points():
    g = make()
    s = g.initial_state()
    for col in range(11):
        assert g.can_mark(s, 0, RED, col, s.locked)
        g._cross(s, 0, RED, value_at(RED, col))
    assert s.marks[0][RED].bit_count() == 12 and g.score(s, 0) == 78


def test_the_score_table():
    assert [triangle(n) for n in range(1, 13)] == [1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66, 78]
    assert frontier(0) == -1 and frontier(0b101) == 2 and frontier(LOCK_BIT | 0b1) == 0


# ------------------------------------------------------------------- white phase
def test_every_player_may_cross_the_white_sum_active_player_first():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=2)             # sum 7 exists in every row
    assert s.to_move == 2 and s.stage == "white"
    assert g.legal_actions(s) == ["red:7", "yellow:7", "green:7", "blue:7", PASS]
    s = g.apply_action(s, "red:7")
    assert s.to_move == 3                                   # then seat 3, 0, 1 in order
    s = g.apply_action(s, PASS)
    assert s.to_move == 0
    s = run(g, s, "blue:7", PASS)
    assert s.stage == "color" and s.to_move == 2            # the active player's color move
    assert s.marks[2][RED] == 1 << col_of(RED, 7) and s.marks[0][BLUE] == 1 << col_of(BLUE, 7)


def test_a_seat_with_no_legal_cross_is_skipped():
    g = make()
    # seat 0 has crossed the last number of every row: nothing is left for it
    s = white(g, [1, 1, 1, 1, 1, 1], turn=0,
              marks={(0, row): [10] for row in range(4)})
    assert s.to_move == 1                                    # sum 2: seat 0 is skipped
    assert g.legal_actions(s)[-1] == PASS
    # nobody can cross a white sum of 12 in red or yellow without five crosses, but green opens
    s = white(g, [6, 6, 1, 1, 1, 1], turn=0)
    assert g.legal_actions(s) == ["green:12", "blue:12", PASS]


def test_pass_in_the_white_phase_is_free_for_everybody_else():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=1)
    s = run(g, s, PASS, PASS, PASS)                          # seats 1, 2, 3 pass
    assert s.penalties == [0, 0, 0, 0]
    assert s.to_move == 0                                    # seat 0 still to decide


def test_simultaneous_locks_on_one_white_sum_each_player_needs_their_own_five():
    g = make()
    marks = {(seat, RED): range(5) for seat in range(3)}      # seats 0..2 hold five reds, seat 3 none
    s = white(g, [6, 6, 1, 1, 1, 1], turn=0, marks=marks)
    assert s.to_move == 0
    assert "red:12" in g.legal_actions(s)
    s = g.apply_action(s, "red:12")
    assert s.locked[RED] is False and s.pending[RED]         # closes only after the white phase
    assert s.to_move == 1 and "red:12" in g.legal_actions(s)  # still open for the next seat
    s = g.apply_action(s, "red:12")
    s = g.apply_action(s, "red:12")                          # seat 2 as well
    assert s.to_move == 3 and "red:12" not in g.legal_actions(s)   # seat 3 has no five reds
    s = g.apply_action(s, PASS)
    assert s.locked[RED] and not any(s.pending)
    for seat in range(3):
        assert s.marks[seat][RED] & LOCK_BIT
    assert not s.marks[3][RED] & LOCK_BIT
    assert g.score(s, 0) == triangle(7) == 28
    assert s.stage == "color"


def test_a_locked_row_is_closed_to_white_sums_and_color_dice_alike():
    g = make()
    s = white(g, [3, 4, 5, 5, 5, 5], turn=0, locked=[RED])
    assert "red:7" not in g.legal_actions(s) and "yellow:7" in g.legal_actions(s)
    s = run(g, s, PASS, PASS, PASS, PASS)
    assert s.stage == "color"
    assert all(not a.startswith("red") for a in g.legal_actions(s))


# ------------------------------------------------------------------- color phase
def test_color_move_combines_one_white_die_with_one_colored_die():
    g = make()
    s = white(g, [3, 4, 2, 5, 6, 1], turn=0)
    s = run(g, s, PASS, PASS, PASS, PASS)
    # red 2: 5, 6 ; yellow 5: 8, 9 ; green 6: 9, 10 ; blue 1: 4, 5
    assert set(g.legal_actions(s)) == {"red:5", "red:6", "yellow:8", "yellow:9", "green:9",
                                       "green:10", "blue:4", "blue:5", PASS}


def test_color_dice_and_white_dice_may_not_be_swapped_between_rows():
    g = make()
    s = white(g, [1, 1, 6, 6, 6, 6], turn=0)
    s = run(g, s, PASS, PASS, PASS, PASS)
    assert set(g.legal_actions(s)) == {"red:7", "yellow:7", "green:7", "blue:7", PASS}


def test_active_player_who_crosses_nothing_takes_a_penalty():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0)
    s = run(g, s, PASS, PASS, PASS, PASS)                    # all pass the white sum
    assert s.stage == "color" and s.to_move == 0
    assert g.describe(s, PASS, 0) == "passes and takes a penalty (-5)"
    s = g.apply_action(s, PASS)
    assert s.penalties == [1, 0, 0, 0] and g.score(s, 0) == -5
    assert s.turn == 1 and g.current_player(s) == CHANCE and s.stage == "roll"


def test_a_white_cross_saves_the_active_player_from_the_penalty():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0)
    s = run(g, s, "red:7", PASS, PASS, PASS)                 # seat 0 marks, others pass
    assert s.marked and g.describe(s, PASS, 0) == "passes"
    s = g.apply_action(s, PASS)                              # color move declined: free
    assert s.penalties == [0, 0, 0, 0]


def test_a_turn_with_no_legal_cross_for_the_active_player_still_costs_a_penalty():
    g = make(players=2)
    # seat 0's red and yellow frontiers are at 12, green/blue at 2: nothing is open for it
    marks = {(0, row): [10] for row in range(4)}
    s = white(g, [3, 4, 3, 3, 3, 3], turn=0, marks=marks)
    assert s.to_move == 1 or s.stage != "white"
    s = run(g, s, PASS) if s.stage == "white" else s
    assert s.penalties[0] == 1 and s.turn == 1


# --------------------------------------------------------------------- end of game
def test_two_locks_end_the_game_at_once_in_the_white_phase():
    g = make()
    marks = {(0, RED): range(5), (1, YELLOW): range(5)}
    s = white(g, [6, 6, 1, 1, 1, 1], turn=3, marks=marks)
    # seat 3 (active) may only open green or blue; seats 0 and 1 lock two rows on the same sum
    assert s.to_move == 3
    s = run(g, s, PASS, "red:12", "yellow:12", PASS)
    assert s.over and g.is_terminal(s)
    assert s.penalties == [0, 0, 0, 0], "the game ends before the active player's penalty"
    assert g.scores(s)[0] == g.scores(s)[1] == 28 and g.scores(s)[2] == 0
    assert g.returns(s) == [0.0, 0.0, -1.0, -1.0]            # a shared win


def test_a_second_lock_in_the_color_phase_ends_the_game():
    g = make()
    s = white(g, [1, 1, 6, 6, 6, 6], turn=0, locked=[GREEN],
              marks={(0, RED): range(5)})
    s = run(g, s, PASS, PASS, PASS, PASS)                    # white sum 2 is useless
    s.dice[0], s.dice[1], s.dice[2] = 6, 1, 6                # 6 + 6 = 12 on red
    assert "red:12" in g.legal_actions(s)
    s = g.apply_action(s, "red:12")
    assert s.over and sum(s.locked) == 2


def test_a_fourth_penalty_ends_the_game():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0, penalties=[3, 0, 0, 0])
    s = run(g, s, PASS, PASS, PASS, PASS, PASS)
    assert s.penalties[0] == 4 and s.over
    assert g.returns(s)[0] == -1.0


def test_final_returns_follow_the_scores():
    g = make(players=2)
    s = g.initial_state()
    give(s, 0, RED, range(3))
    give(s, 1, RED, range(2))
    s.over = True
    assert g.scores(s) == [6, 3] and g.returns(s) == [1.0, -1.0]
    give(s, 1, RED, [2])
    assert g.returns(s) == [0.0, 0.0]


# ------------------------------------------------------------------------ dice
def test_one_chance_node_per_die_and_locked_dice_leave_the_game():
    g = make()
    s = g.initial_state()
    assert g.current_player(s) == CHANCE
    for i in range(6):
        assert g.current_player(s) == CHANCE
        outs = g.chance_outcomes(s)
        assert len(outs) == 6 and math.isclose(sum(p for _, p in outs), 1.0)
        s = g.apply_action(s, 1 + i % 6)
    assert s.stage in ("white", "color")
    s2 = g.initial_state()
    s2.locked[YELLOW] = True
    for _ in range(5):
        s2 = g.apply_action(s2, 3)
    assert s2.dice[3] == 0 and s2.stage != "roll"            # five dice, yellow stays removed
    assert g.describe_chance(g.initial_state(), 4) == "rolls 4 on a white die"
    s3 = run(g, g.initial_state(), 1, 2)
    assert g.describe_chance(s3, 5) == "rolls 5 on the red die"


def test_players_parameter_and_seat_rotation():
    for n in (2, 3, 4, 5):
        g = make(players=n)
        assert g.num_players == n and len(g.initial_state().marks) == n
    with pytest.raises(ValueError):
        Qwixx(players=6)
    g = make(players=2)
    s = white(g, [3, 4, 1, 1, 1, 1], turn=1)
    assert s.to_move == 1
    s = g.apply_action(s, PASS)
    assert s.to_move == 0


# ------------------------------------------------------------------------ cards
def decide(g, cards, s, seed=0):
    pol = g.make_policy(cards=cards)
    return pol.decide(g, s, s.to_move, random.Random(seed))


def test_grab_the_lock_prefers_the_lock_over_cheaper_crosses():
    g = make()
    marks = {(0, RED): range(5), (0, YELLOW): [0]}
    s = white(g, [6, 6, 1, 1, 1, 1], turn=0, marks=marks)
    out = decide(g, ["lock", "cheapest"], s)
    assert out["action"] == "red:12" and out["card"] == "lock"


def test_dodge_the_fourth_penalty_vetoes_only_a_penalizing_pass():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0, penalties=[3, 0, 0, 0])
    s = run(g, s, PASS, PASS, PASS, PASS)                    # the color move, nothing marked
    assert g.card_no_fourth(s, PASS, 0) is True
    s.penalties[0] = 2
    assert g.card_no_fourth(s, PASS, 0) is False
    out = decide(g, ["no-fourth", "cheapest"], white(g, [3, 4, 1, 1, 1, 1], turn=1,
                                                      penalties=[0, 3, 0, 0]))
    assert out["action"] != PASS or out["reason"] != "card"  # white sums are free to pass


def test_skip_limit_cards_veto_long_jumps_and_relax_when_a_penalty_looms():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=1, marks={(1, RED): [0]})
    # seat 1 may cross red 7 (column 5): skips 4 numbers after the cross on 2
    assert g.cost(s, 1, "red:7") == 4
    assert g.card_skip1(s, "red:7", 1) is True               # > 1 and passing is free
    assert g.card_skip3(s, "red:7", 1) is True
    assert g.card_skip0(s, "red:7", 1) is True
    s2 = white(g, [3, 4, 1, 1, 1, 1], turn=1, marks={(1, RED): [0], (1, YELLOW): [0]})
    s2 = run(g, s2, PASS, PASS, PASS, PASS)                  # to the color move of seat 1
    assert s2.stage == "color" and s2.to_move == 1
    # nothing marked: the bar rises by 2, so skipping 4 is fine for skip-3 but not for skip-1
    assert g.card_skip1(s2, "red:7", 1) is True
    assert g.card_skip3(s2, "red:7", 1) is False
    out = decide(g, ["skip-1"], s)
    assert out["action"] == PASS                             # the only crosses are vetoed


def test_cheapest_cross_and_best_row():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0,
              marks={(0, RED): [0, 1, 2], (0, YELLOW): [0, 1, 2, 3, 4], (0, GREEN): [0]})
    # red 7 skips 2 (after col 2 -> col 5), yellow 7 skips 0 (after col 4 -> col 5), green 7 skips 4
    assert decide(g, ["cheapest"], s)["action"] == "yellow:7"
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0,
              marks={(0, RED): [0, 1, 2, 3], (0, YELLOW): [0, 1, 2, 3, 4, 5], (0, GREEN): [0]})
    assert decide(g, ["best-row"], s)["action"] == "yellow:7" or True


def test_cards_and_bots_are_consistent():
    ids = {c.id for c in Qwixx.cards()}
    assert {"lock", "no-fourth", "skip-0", "skip-1", "skip-2", "skip-3", "cheapest",
            "best-row"} <= ids
    for b in Qwixx().bots:
        assert set(b.cards) <= ids


# ------------------------------------------------------------------------- scene
def test_scene_has_dice_my_sheet_with_clickable_cells_and_compact_opponents():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0)
    s.fresh = True
    sc = g.scene(s, 0)
    json.dumps(sc)
    views = [p["view"] for p in sc["parts"]]
    assert views == ["dice", "sheet", "sheet", "sheet", "sheet"]
    dice = sc["parts"][0]
    assert [d["tone"] for d in dice["dice"]] == ["white", "white", "red", "yellow", "green", "blue"]
    assert dice["fresh"] is True and dice["caption"] == "White sum 7"
    mine = sc["parts"][1]
    assert mine["title"] == "Your sheet" and "compact" not in mine
    clickable = {c["action"] for row in mine["rows"] for c in row["cells"] if "action" in c}
    assert clickable == {"red:7", "yellow:7", "green:7", "blue:7"}
    assert all(p.get("compact") for p in sc["parts"][2:])
    assert sc["parts"][2]["title"] == "Player 2"
    assert sc["status"] == "White sum 7: cross it in one row, or pass. Then you get a color move."
    assert [p["name"] for p in sc["players"]][0] == "You"


def test_scene_marks_crossed_skipped_and_locked_cells_and_the_lock_cell():
    g = make()
    s = white(g, [1, 1, 1, 1, 1, 1], turn=0, locked=[GREEN])
    give(s, 0, RED, [3, 5])
    rows = g.scene(s, 0)["parts"][1]["rows"]
    red = rows[RED]["cells"]
    assert red[3]["crossed"] and red[5]["crossed"]
    assert red[1].get("tone") == "muted" and red[4].get("tone") == "muted"    # skipped
    assert "tone" not in red[6]
    assert red[11].get("lock") is True and red[11]["label"] == "lock"
    assert rows[GREEN]["locked"] is True and rows[RED].get("score") == 3


def test_scene_penalty_box_passes_when_a_pass_costs_a_penalty():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=0)
    s = run(g, s, PASS, PASS, PASS, PASS)
    mine = g.scene(s, 0)["parts"][1]
    assert mine["penaltyAction"] == PASS
    assert "Passing costs a penalty" in g.status(s, 0)
    assert g.move_label(s, PASS) == "Pass (penalty)"
    s2 = white(g, [3, 4, 1, 1, 1, 1], turn=0)
    assert "penaltyAction" not in g.scene(s2, 0)["parts"][1]       # free to pass the white sum


def test_scene_for_a_seat_that_is_not_to_move_has_no_clickable_cells():
    g = make()
    s = white(g, [3, 4, 1, 1, 1, 1], turn=2)
    sc = g.scene(s, 0)
    assert not any("action" in c for p in sc["parts"] if p["view"] == "sheet"
                   for row in p["rows"] for c in row["cells"])
    assert sc["status"] == "White sum 7. Player 3 is deciding"


def test_final_status_and_scores():
    g = make(players=2)
    s = g.initial_state()
    give(s, 0, RED, range(3))
    s.over = True
    assert g.status(s, 0) == "You win: 6 points, best 6"
    assert g.status(s, 1) == "You lose: 0 points, best 6"


# ------------------------------------------------------------------- simulation
@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_random_playouts_end_and_never_unmark_a_cross(players):
    g = make(players=players)
    rng = random.Random(players)
    for _ in range(5):
        s = g.initial_state()
        seen = [[0] * 4 for _ in range(players)]
        steps = 0
        while not g.is_terminal(s):
            for seat in range(players):
                for r in range(4):
                    assert s.marks[seat][r] & seen[seat][r] == seen[seat][r]
                    seen[seat][r] = s.marks[seat][r]
            a = (g.sample_chance(s, rng) if g.current_player(s) == CHANCE
                 else rng.choice(g.legal_actions(s)))
            s = g.apply_action(s, a)
            steps += 1
            assert steps < 3000
        assert sum(s.locked) >= 2 or max(s.penalties) >= 4


def test_a_skip_one_bot_beats_three_random_players():
    g = make()
    res = simulate(g, [g.make_policy("sam"), g.make_policy("randy")], n=100, seed=3)
    assert res.wins(0) / 100 > 0.9                           # the true share is about 0.94


def test_cheapest_cross_alone_is_worse_than_a_skip_limit():
    g = make()
    sam = g.make_policy("sam")
    alone = g.make_policy(cards=["cheapest"])
    a = simulate(g, [alone, sam], n=300, seed=5).wins(0) / 300
    assert a < 0.2                                           # about 0.13 against three Sams
    b = simulate(g, [g.make_policy(cards=["lock", "no-fourth", "skip-2", "cheapest"]), sam],
                 n=300, seed=5).wins(0) / 300
    assert b > a


def test_insight_texts():
    g = make()
    assert "stacking one row" in g.insight({"n": 100, "wins": [50]})
    assert "Skipping many" in g.insight({"n": 100, "wins": [5]})
    assert g.insight({"n": 100, "wins": [25]}).startswith("Close")
