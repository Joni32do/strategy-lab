"""Snakes & Ladders: the board, bouncing, die choice, cards, scene, simulation."""

from __future__ import annotations

import json
import math
import random

from strategy_lab.core import CHANCE
from strategy_lab.core.match import simulate
from strategy_lab.families.dice import RollAndMoveGame
from strategy_lab.games.snakes import JUMPS, SnakesAndLadders, SnakesState, square_index


def state(p0=0, p1=0, dice=(3, 5), turn=0):
    return SnakesState(to_move=turn, turn=turn, pos=[p0, p1], dice=dice)


def decide(g, cards, s, seed=0):
    pol = g.make_policy(cards=cards)
    return pol.decide(g, s, s.turn, random.Random(seed))


# --------------------------------------------------------------------------- board
def test_classic_board_has_nine_ladders_and_ten_snakes():
    ladders = {a: b for a, b in JUMPS.items() if b > a}
    snakes = {a: b for a, b in JUMPS.items() if b < a}
    assert len(ladders) == 9 and len(snakes) == 10
    assert all(1 <= a <= 99 and 1 <= b <= 100 for a, b in JUMPS.items())
    feet = set(JUMPS)
    assert not feet & set(JUMPS.values()) - {100}, "a jump must not end on another jump"
    assert 100 not in JUMPS


def test_serpentine_numbering_starts_bottom_left():
    assert square_index(1) == 90 and square_index(10) == 99
    assert square_index(11) == 89 and square_index(20) == 80      # the row turns around
    assert square_index(91) == 9 and square_index(100) == 0       # the finish is top left
    assert sorted(square_index(n) for n in range(1, 101)) == list(range(100))


# --------------------------------------------------------------------------- moves
def test_landing_ladders_snakes_and_bounce():
    g = SnakesAndLadders()
    assert g.landing(0, 1) == (1, 38)            # the foot of a ladder at the very start
    assert g.landing(12, 4) == (16, 6)           # a snake's head
    assert g.landing(5, 2) == (7, 7)             # plain square
    assert g.landing(97, 3) == (100, 100)        # exact finish
    # 98 + 4 = 102 bounces to 98, which is a snake head: slide down to 78
    assert g.landing(98, 4) == (98, 78)
    assert g.landing(96, 6) == (98, 78)          # 102 -> 98 -> snake to 78
    assert g.landing(99, 2) == (99, 99)          # 99 -> 100 -> back to 99
    assert g.landing(74, 6) == (80, 100)         # the ladder 80 -> 100 wins


def test_overshoot_without_bounce_leaves_the_token_in_place():
    g = SnakesAndLadders(bounce=False)
    assert g.landing(98, 4) == (98, 98)
    assert g.landing(97, 3) == (100, 100)        # exact landing still wins
    s = g.apply_action(state(97, 0, dice=(4, 4)), 4)
    assert s.pos[0] == 97 and not g.is_terminal(s)
    assert g.describe(state(97, 0, dice=(4, 4)), 4, 0) == "takes the 4 but overshoots 100 and stays on 97"


def test_advance_helper_modes():
    adv = RollAndMoveGame.advance
    assert adv(98, 4, 100, "bounce").dest == 98 and adv(98, 4, 100, "bounce").bounced
    assert adv(98, 4, 100, "bounce").path == (99, 100, 99, 98)
    assert adv(90, 5, 100, "bounce").dest == 95 and not adv(90, 5, 100, "bounce").bounced
    assert adv(58, 6, 60, "stop").dest == 60 and adv(58, 6, 60, "stop").path == (59, 60)
    assert adv(38, 5, 39, "loop").dest == 3 and 0 in adv(38, 5, 39, "loop").path


def test_winning_move_ends_the_game():
    g = SnakesAndLadders()
    s = g.apply_action(state(97, 40, dice=(3, 6)), 3)
    assert g.is_terminal(s) and g.winner(s) == 0
    assert g.returns(s) == [1.0, -1.0]
    s = g.apply_action(state(40, 94, dice=(6, 6), turn=1), 6)
    assert g.winner(s) == 1


def test_a_move_passes_the_turn_to_a_chance_node_for_the_other_seat():
    g = SnakesAndLadders()
    s = g.apply_action(state(10, 20, dice=(2, 5)), 5)
    assert s.pos == [15, 20] and g.current_player(s) == CHANCE and s.turn == 1
    s = g.apply_action(s, "1-1")
    assert g.current_player(s) == 1 and s.dice == (1, 1)
    assert g.legal_actions(s) == [1]                # a double offers one action


def test_two_different_dice_offer_two_actions_in_order():
    g = SnakesAndLadders()
    assert g.legal_actions(state(dice=(2, 6))) == [2, 6]
    assert g.legal_actions(state(dice=(4, 4))) == [4]


def test_chance_node_rolls_the_unordered_pair():
    g = SnakesAndLadders()
    outs = g.chance_outcomes(g.initial_state())
    assert len(outs) == 21 and math.isclose(sum(p for _, p in outs), 1.0)
    probs = dict(outs)
    assert math.isclose(probs["3-3"], 1 / 36) and math.isclose(probs["2-5"], 2 / 36)
    info = g.chance_info(g.initial_state(), "2-5")
    assert math.isclose(info["entropy"], 4.3366, abs_tol=1e-3)
    assert g.describe_chance(g.initial_state(), "2-5") == "rolls 2 and 5"
    assert g.describe_chance(g.initial_state(), "4-4") == "rolls double 4"


def test_captions_describe_the_move_without_the_actor():
    g = SnakesAndLadders()
    assert g.describe(state(0, 0), 1, 0) == "takes the 1 from the start to 1, climbs the ladder to 38"
    assert g.describe(state(12, 0), 4, 0) == "takes the 4 from 12 to 16, slides down the snake to 6"
    assert g.describe(state(97, 0), 3, 0) == "takes the 3 from 97 to 100, and wins"
    assert g.describe(state(98, 0), 4, 0) == ("takes the 4, bounces off 100 and lands on 98, "
                                              "slides down the snake to 78")


# --------------------------------------------------------------------------- cards
def test_photo_finish_takes_the_winning_die():
    g = SnakesAndLadders()
    s = state(94, 0, dice=(1, 6))                    # 94 + 6 = 100
    assert decide(g, ["sniper"], s)["action"] == 6
    s = state(74, 0, dice=(3, 6))                    # 74 + 6 = 80: the ladder to 100
    assert decide(g, ["sniper"], s)["action"] == 6


def test_ladder_lover_prefers_the_foot_of_the_highest_ladder():
    g = SnakesAndLadders()
    assert decide(g, ["ladder"], state(0, 0, dice=(1, 4)))["action"] == 1    # 1 -> 38 beats 4 -> 14
    assert decide(g, ["ladder"], state(0, 0, dice=(2, 3)))["reason"] == "random"


def test_snake_dodger_vetoes_snake_heads_but_never_the_last_option():
    g = SnakesAndLadders()
    out = decide(g, ["dodge"], state(12, 0, dice=(4, 2)))     # 12 + 4 = 16 is a snake head
    assert out["action"] == 2 and out["vetoed"] == [("dodge", [4])]
    out = decide(g, ["dodge"], state(12, 0, dice=(4, 4)))     # no choice: it must go
    assert out["action"] == 4


def test_no_overshoot_vetoes_dice_past_100():
    g = SnakesAndLadders()
    out = decide(g, ["no-bounce"], state(96, 0, dice=(3, 5)))
    assert out["action"] == 3 and out["vetoed"] == [("no-bounce", [5])]


def test_far_sighted_counts_snakes_ladders_and_bounces():
    g = SnakesAndLadders()
    assert decide(g, ["far"], state(10, 0, dice=(1, 6)))["action"] == 1      # 11 beats 16 -> 6
    assert decide(g, ["far"], state(0, 0, dice=(1, 6)))["action"] == 1       # 1 -> 38 beats 6
    assert decide(g, ["far"], state(97, 0, dice=(1, 3)))["action"] == 3      # 100


def test_speed_cards():
    g = SnakesAndLadders()
    assert decide(g, ["big"], state(dice=(2, 5)))["action"] == 5
    assert decide(g, ["small"], state(dice=(2, 5)))["action"] == 2


# --------------------------------------------------------------------------- scene
def test_scene_board_dice_and_scoreboard():
    g = SnakesAndLadders()
    s = g.apply_action(g.initial_state(), "2-5")
    sc = g.scene(s, 0)
    json.dumps(sc)
    board, dice = sc["parts"]
    assert board["view"] == "grid" and board["rows"] == board["cols"] == 10
    assert len(board["cells"]) == 100 and board["cells"][90]["label"] == "1"
    assert board["cells"][0]["label"] == "100" and board["cells"][0]["tone"] == "goal"
    ladder_cell = board["cells"][square_index(4)]
    assert ladder_cell["tone"] == "ladder" and ladder_cell["badge"] == "^14"
    snake_cell = board["cells"][square_index(16)]
    assert snake_cell["tone"] == "snake" and snake_cell["badge"] == "v6"
    assert len(board["links"]) == 19
    assert {(l["kind"]) for l in board["links"]} == {"up", "down"}
    assert dice["view"] == "dice" and dice["fresh"] is True
    assert [d["action"] for d in dice["dice"]] == [2, 5]
    assert sc["players"][0]["active"] is True and sc["players"][0]["score"] == "start"
    assert sc["status"] == "You rolled 2 and 5: pick a die"


def test_scene_tokens_and_inert_dice_for_the_other_seat():
    g = SnakesAndLadders()
    s = state(7, 30, dice=(2, 5))
    board, dice = g.scene(s, 1)["parts"]
    assert board["cells"][square_index(7)]["pieces"] == [{"owner": 0, "shape": "token"}]
    assert board["cells"][square_index(30)]["pieces"][0]["owner"] == 1
    assert all("action" not in d for d in dice["dice"])      # seat 0 is to move, viewer is seat 1
    assert g.scene(s, 1)["status"] == "Player 1 rolled 2 and 5 and is choosing"


def test_last_move_is_marked():
    g = SnakesAndLadders()
    s = g.apply_action(state(10, 0, dice=(2, 5)), 5)
    board = g.scene(s, 0)["parts"][0]
    assert board["cells"][square_index(15)]["tone"] == "last"


def test_timeout_goes_to_the_leader():
    g = SnakesAndLadders()
    assert g.timeout_returns(state(60, 40)) == [1.0, -1.0]
    assert g.timeout_returns(state(40, 60)) == [-1.0, 1.0]
    assert g.timeout_returns(state(50, 50)) == [0.0, 0.0]


def test_key_ignores_the_last_move_marker():
    g = SnakesAndLadders()
    a, b = state(3, 4), state(3, 4)
    b.last = (0, 3, 3)
    b.fresh = True
    assert g.key(a) == g.key(b)


# ---------------------------------------------------------------------- simulation
def win_rate(g, a, b, n, seed=3):
    res = simulate(g, [g.make_policy(a), g.make_policy(b)], n=n, seed=seed)
    assert res.to_json()["timeouts"] == 0
    return res.wins(0) / n


def test_looking_ahead_beats_random_by_a_wide_margin():
    g = SnakesAndLadders()
    assert win_rate(g, "lena", "randy", 300) > 0.78       # true rate about 0.86
    assert win_rate(g, "cleo", "harry", 300) > 0.7        # about 0.80


def test_sensible_policies_are_close_to_a_coin_flip():
    g = SnakesAndLadders()
    assert 0.38 < win_rate(g, "lena", "cleo", 400) < 0.68   # true rate about 0.53


def test_taking_the_smaller_die_is_worse_than_random():
    g = SnakesAndLadders()
    res = simulate(g, [g.make_policy(cards=["small"]), g.make_policy("randy")], n=500, seed=5)
    assert res.wins(0) / 500 < 0.5


def test_no_bounce_variant_plays_to_the_end():
    g = SnakesAndLadders(bounce=False)
    res = simulate(g, [g.make_policy("lena"), g.make_policy("randy")], n=100, seed=2)
    assert res.to_json()["timeouts"] == 0
    assert res.wins(0) > res.wins(1)


def test_insight_texts():
    g = SnakesAndLadders()
    assert g.insight({"n": 100, "wins": [52, 48]}).startswith("Dead even")
    assert g.insight({"n": 100, "wins": [80, 20]}).startswith("A real edge: 80 to 20")
    assert "Far sighted" in g.insight({"n": 100, "wins": [20, 80]})
