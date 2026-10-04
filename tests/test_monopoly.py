"""Monopoly: board data, turn machine, rent, building, jail, bankruptcy, cards, scene."""

from __future__ import annotations

import json
import math
import random

from strategy_lab.core import CHANCE
from strategy_lab.core.match import play_out, simulate
from strategy_lab.games.monopoly import (
    CARDS, GROUPS, RAILROADS, SQUARES, UTILITIES, Monopoly)

BOARDWALK, PARK, MED, BALTIC = 39, 37, 1, 3
ORIENTAL, VERMONT, CONNECTICUT = 6, 8, 9


def fresh(**kw):
    """A start-of-game state; it waits at the first chance node (seat 0 rolls)."""
    g = Monopoly(**kw)
    return g, g.initial_state()


def roll(g, s, a):
    assert g.current_player(s) == CHANCE and s.stage in ("roll", "jailroll"), s.stage
    return g.apply_action(s, a)


def decide(g, cards, s, seed=0):
    pol = g.make_policy(cards=cards)
    return pol.decide(g, s, s.turn, random.Random(seed))


def give(s, seat, squares):
    for i in squares:
        s.owner[i] = seat


# ------------------------------------------------------------------------ board
def test_board_has_40_squares_and_standard_prices():
    assert len(SQUARES) == 40
    assert [len(g) for g in GROUPS] == [2, 3, 3, 3, 3, 3, 3, 2]
    assert len(RAILROADS) == 4 and len(UTILITIES) == 2
    prices = sorted(sq[3] for sq in SQUARES if sq[1] in ("prop", "rr", "util"))
    assert sum(prices) == 4 * 200 + 2 * 150 + (60 + 60 + 100 + 100 + 120 + 140 + 140 + 160
                                                + 180 + 180 + 200 + 220 + 220 + 240 + 260
                                                + 260 + 280 + 300 + 300 + 320 + 350 + 400)
    assert SQUARES[BOARDWALK][:4] == ("Boardwalk", "prop", 7, 400)
    assert SQUARES[30][1] == "gotojail" and SQUARES[10][1] == "jail"


def test_start_state_waits_for_seat_0s_roll():
    g, s = fresh()
    assert s.cash == [1500, 1500] and g.current_player(s) == CHANCE and s.turn == 0
    outs = g.chance_outcomes(s)
    assert len(outs) == 21 and math.isclose(sum(p for _, p in outs), 1.0)


# ------------------------------------------------------------------ movement
def test_roll_moves_the_token_and_lands_on_a_buyable_street():
    g, s = fresh()
    s = roll(g, s, "1-2")                                     # 3: Baltic Ave
    assert s.pos[0] == 3 and s.stage == "buy" and s.buy_sq == 3
    assert g.legal_actions(s) == ["buy", "skip"] and g.current_player(s) == 0
    s = g.apply_action(s, "buy")
    assert s.owner[3] == 0 and s.cash[0] == 1440
    assert s.turn == 1 and g.current_player(s) == CHANCE      # nothing to build: next turn


def test_skipping_a_purchase_leaves_the_street_unowned_no_auction():
    g, s = fresh()
    s = g.apply_action(roll(g, s, "1-2"), "skip")
    assert s.owner[3] == -1 and s.cash[0] == 1500 and s.turn == 1


def test_passing_go_pays_200_and_landing_on_it_too():
    g, s = fresh()
    s.pos[0] = 38
    s = roll(g, s, "1-3")                                     # 38 + 4 = 42 -> square 2 (Chest)
    assert s.cash[0] == 1700 and s.pos[0] == 2 and s.stage == "card"
    g, s = fresh()
    s.pos[0] = 36
    s = roll(g, s, "1-3")                                     # lands exactly on GO
    assert s.pos[0] == 0 and s.cash[0] == 1700


def test_a_double_gives_another_roll_and_a_third_goes_to_jail():
    g, s = fresh()
    s = roll(g, s, "2-2")                                     # square 4: income tax, then again
    assert s.turn == 0 and s.extra and g.current_player(s) == CHANCE and s.doubles == 1
    s = roll(g, s, "3-3")                                     # square 10: just visiting
    assert s.turn == 0 and s.doubles == 2 and not s.jail[0]
    s = roll(g, s, "1-1")
    assert s.jail[0] and s.pos[0] == 10 and s.turn == 1       # a third double: straight to jail
    assert s.cash[0] == 1300                                  # no GO money, only the tax
    g, s = fresh()
    assert g.describe_chance(s, "1-2") == "rolls 1 and 2 and lands on Baltic Ave"
    assert g.describe_chance(s, "1-1") == "rolls double 1 and lands on Community Chest"


def test_go_to_jail_square_and_the_jail_card():
    g, s = fresh()
    s.pos[0] = 27
    s = roll(g, s, "1-2")                                     # 30: Go To Jail
    assert s.jail[0] and s.pos[0] == 10 and s.turn == 1
    g, s = fresh()
    s.pos[0] = 4
    s.stage = "card"
    s.to_move = CHANCE
    s = g.apply_action(s, 6)                                  # "Go directly to jail"
    assert s.jail[0] and s.turn == 1


# -------------------------------------------------------------------------- rent
def test_rent_rules_street_set_railroads_utilities():
    g, s = fresh()
    give(s, 1, [MED])
    assert g.rent(s, MED) == 2
    give(s, 1, [BALTIC])
    assert g.rent(s, MED) == 4                                # double on a complete set
    s.houses[MED] = 2
    assert g.rent(s, MED) == 2 * 15
    s.houses[MED] = 4
    assert g.rent(s, MED) == 2 * 40
    give(s, 1, [5])
    assert g.rent(s, 5) == 25
    give(s, 1, [15, 25])
    assert g.rent(s, 5) == 100
    give(s, 1, [35])
    assert g.rent(s, 5) == 200
    s.total = 8
    give(s, 1, [12])
    assert g.rent(s, 12) == 4 * 8
    give(s, 1, [28])
    assert g.rent(s, 12) == 10 * 8


def test_landing_on_an_opponents_street_pays_rent():
    g, s = fresh()
    give(s, 1, [3])
    s = roll(g, s, "1-2")
    assert s.cash == [1496, 1504]
    assert s.turn == 1 and g.current_player(s) == CHANCE


def test_rent_caption():
    g, s = fresh()
    give(s, 1, [3])
    assert g.describe_chance(s, "1-2") == "rolls 1 and 2 and lands on Baltic Ave, pays $4 rent"


def test_income_tax_and_luxury_tax():
    g, s = fresh()
    s.pos[0] = 1
    s = roll(g, s, "1-2")                                     # 4: Income Tax
    assert s.cash[0] == 1300
    g, s = fresh()
    s.pos[0] = 35
    s = roll(g, s, "1-2")                                     # 38: Luxury Tax
    assert s.cash[0] == 1400


# ---------------------------------------------------------------------- building
def test_building_needs_the_whole_group_and_goes_evenly():
    g, s = fresh()
    give(s, 0, [MED])
    assert g.build_options(s, 0) == []
    give(s, 0, [BALTIC])
    assert g.build_options(s, 0) == [MED, BALTIC]
    s.houses[MED] = 1
    assert g.build_options(s, 0) == [BALTIC]                  # even building
    s.houses[BALTIC] = 1
    assert g.build_options(s, 0) == [MED, BALTIC]
    s.houses[MED] = s.houses[BALTIC] = 4
    assert g.build_options(s, 0) == []                        # no hotels
    s.houses = [0] * 40
    s.cash[0] = 49
    assert g.build_options(s, 0) == []                        # cannot afford a $50 house


def test_build_decision_flow_and_cost():
    g, s = fresh()
    give(s, 0, [MED, BALTIC])
    s.pos[0] = 0
    s = roll(g, s, "1-2")                                     # lands on own Baltic: after -> build
    assert s.stage == "build" and g.current_player(s) == 0
    assert g.legal_actions(s) == ["build:1", "build:3", "done"]
    s = g.apply_action(s, "build:1")
    assert s.houses[1] == 1 and s.cash[0] == 1450 and s.stage == "build"
    assert g.legal_actions(s) == ["build:3", "done"]
    s = g.apply_action(s, "done")
    assert s.turn == 1 and g.current_player(s) == CHANCE


# -------------------------------------------------------------------------- jail
def jailed(cash=1500):
    g, s = fresh()
    s.jail[0] = True
    s.pos[0] = 10
    s.cash[0] = cash
    s.stage = "start"
    return g, g.settle(s)


def test_in_jail_you_may_pay_before_rolling():
    g, s = jailed()
    assert s.stage == "jail" and g.legal_actions(s) == ["pay", "wait"]
    s = g.apply_action(s, "pay")
    assert s.cash[0] == 1450 and not s.jail[0] and s.stage == "roll"


def test_doubles_free_you_and_you_move_by_the_roll_without_another_turn():
    g, s = jailed()
    s = g.apply_action(s, "wait")
    s = roll(g, s, "2-2")
    assert not s.jail[0] and s.pos[0] == 14 and s.stage == "buy" and not s.extra
    s = g.apply_action(s, "skip")
    assert s.turn == 1                                        # no extra roll for jail doubles
    g, s = jailed()
    s = g.apply_action(s, "wait")
    assert g.describe_chance(s, "2-2") == "rolls double 2 and leaves jail and lands on Virginia Ave"


def test_three_failures_cost_50_and_move_you_by_the_roll():
    g, s = jailed()
    for _ in range(2):
        s = g.apply_action(s, "wait")
        s = roll(g, s, "1-2")
        assert s.jail[0] and s.turn == 1
        s = roll(g, s, "1-2")                                 # the opponent rolls and moves on
        s = g.apply_action(s, "skip") if s.stage == "buy" else s
        while s.turn == 1:
            s = g.apply_action(s, g.legal_actions(s)[-1]) if g.current_player(s) >= 0 \
                else g.apply_action(s, "1-2")
    s = g.apply_action(s, "wait")
    s = roll(g, s, "1-2")
    assert not s.jail[0] and s.cash[0] == 1450 and s.pos[0] == 13


def test_a_broke_prisoner_cannot_pay_and_rolls_straight_away():
    g, s = jailed(cash=30)
    assert s.stage == "jailroll" and g.current_player(s) == CHANCE


# -------------------------------------------------------------------- bankruptcy
def test_forced_sales_go_house_first_then_property_at_half_price():
    g, s = fresh()
    give(s, 0, [MED, BALTIC])
    s.houses[MED] = 2
    s.houses[BALTIC] = 1
    s.cash[0] = 10
    g.charge(s, 0, 60)                                        # short by 50: two houses at $25
    assert s.houses[MED] == 1 and s.houses[BALTIC] == 0       # from the tallest street first
    assert s.cash[0] == 0 and s.dead < 0 and s.owner[MED] == 0
    g, s = fresh()
    give(s, 0, [MED, BALTIC])
    s.cash[0] = 0
    g.charge(s, 0, 40)                                        # no houses: sells a $60 street for $30 twice
    assert s.dead < 0 and s.cash[0] == 20 and sum(1 for o in s.owner if o == 0) == 0


def test_not_enough_assets_means_bankruptcy_and_the_other_player_wins():
    g, s = fresh()
    s.cash[0] = 0
    g.charge(s, 0, 500, to=1)
    assert s.dead == 0 and s.cash[1] == 2000
    s.over = True
    assert g.winner(s) == 1 and g.returns(s) == [-1.0, 1.0]


def test_round_limit_then_net_worth_decides():
    g, s = fresh(rounds=20)
    s.rounds = 39
    s.stage = "after"
    s = g.settle(s)
    assert s.over and g.is_terminal(s)
    assert g.winner(s) is None                                # equal cash, nothing owned
    s2 = g.initial_state()
    s2.cash[1] = 1600
    s2.over = True
    assert g.winner(s2) == 1 and g.timeout_returns(s2) == [-1.0, 1.0]
    assert g.net_worth(s2, 1) == 1600


def test_net_worth_counts_prices_and_houses_at_cost():
    g, s = fresh()
    give(s, 0, [MED, BALTIC, 5])
    s.houses[MED] = 2
    assert g.net_worth(s, 0) == 1500 + 60 + 60 + 200 + 2 * 50


# ---------------------------------------------------------------------- the deck
def test_card_deck_effects():
    def draw(i, cash=1500, houses=0):
        g, s = fresh()
        s.stage, s.to_move, s.cash[0] = "card", CHANCE, cash
        if houses:
            give(s, 0, [MED, BALTIC])
            s.houses[MED] = houses
        return g, g.apply_action(s, i)
    assert draw(0)[1].cash[0] == 1700 and draw(2)[1].cash[0] == 1550
    assert draw(3)[1].cash[0] == 1450 and draw(4)[1].cash[0] == 1400
    s = draw(5)[1]
    assert s.pos[0] == 0 and s.cash[0] == 1700
    s = draw(6)[1]
    assert s.jail[0] and s.pos[0] == 10
    assert draw(7, houses=3)[1].cash[0] == 1500 - 75
    assert draw(7)[1].cash[0] == 1500                          # no houses: no repairs
    g, s = fresh()
    s.stage = "card"
    outs = g.chance_outcomes(s)
    assert len(outs) == len(CARDS) == 8 and math.isclose(sum(p for _, p in outs), 1.0)
    assert g.action_label(s, 6) == "Go directly to jail"


# ------------------------------------------------------------------------- cards
def buy_state(square, cash=1500, owners=()):
    g, s = fresh()
    s.stage, s.buy_sq, s.to_move, s.cash[0] = "buy", square, 0, cash
    for sq, seat in owners:
        s.owner[sq] = seat
    return g, s


def test_buy_cards():
    g, s = buy_state(BOARDWALK)
    assert decide(g, ["buy-all"], s)["action"] == "buy"
    assert decide(g, ["bargain"], s)["card"] is None          # $400 is not a bargain
    g, s = buy_state(MED)
    assert decide(g, ["bargain"], s)["action"] == "buy"
    g, s = buy_state(5)
    assert decide(g, ["tycoon"], s)["action"] == "buy"
    g, s = buy_state(BALTIC, owners=[(MED, 0)])
    assert decide(g, ["set-hunter"], s)["action"] == "buy"
    g, s = buy_state(BALTIC)
    assert decide(g, ["set-hunter"], s)["card"] is None
    g, s = buy_state(BALTIC, owners=[(MED, 1)])
    assert decide(g, ["blocker"], s)["action"] == "buy"


def test_cash_cushion_vetoes_purchases_and_houses_below_300():
    g, s = buy_state(BOARDWALK, cash=650)                     # 650 - 400 = 250 < 300
    out = decide(g, ["cushion", "buy-all"], s)
    assert out["action"] == "skip" and out["vetoed"] == [("cushion", ["buy"])]
    g, s = buy_state(BOARDWALK, cash=700)
    assert decide(g, ["cushion", "buy-all"], s)["action"] == "buy"
    g, s = fresh()
    give(s, 0, [MED, BALTIC])
    s.cash[0] = 340
    s.stage, s.to_move = "build", 0
    assert g.card_cushion(s, "build:1", 0) is True
    assert g.card_cushion(s, "done", 0) is False


def test_builder_and_spread_and_jail_cards():
    g, s = fresh()
    give(s, 0, [ORIENTAL, VERMONT, CONNECTICUT, MED, BALTIC])
    s.stage, s.to_move = "build", 0
    acts = g.legal_actions(s)
    assert decide(g, ["builder"], s)["action"] == f"build:{CONNECTICUT}"       # base rent 8 is highest
    s.houses[MED] = s.houses[BALTIC] = 1
    s.houses[ORIENTAL] = 1
    assert "build:1" in acts
    assert decide(g, ["spread"], s)["action"] in (f"build:{VERMONT}", f"build:{CONNECTICUT}")
    g, s = jailed()
    assert decide(g, ["pay-jail"], s)["action"] == "pay"
    assert decide(g, ["sit-jail"], s)["action"] == "wait"


def test_cards_and_bots_are_consistent():
    ids = {c.id for c in Monopoly.cards()}
    assert ids == {"buy-all", "set-hunter", "blocker", "tycoon", "bargain", "cushion",
                   "builder", "spread", "pay-jail", "sit-jail"}
    for b in Monopoly().bots:
        assert set(b.cards) <= ids
    assert Monopoly.family()["id"] == "roll-and-move"


# ------------------------------------------------------------------------ scene
def test_scene_has_a_ring_with_group_tones_owners_houses_and_tokens():
    g, s = fresh()
    give(s, 1, [MED, BALTIC])
    s.houses[MED] = 2
    s = roll(g, s, "1-2")
    sc = g.scene(s, 0)
    json.dumps(sc)
    track = sc["parts"][0]
    assert track["view"] == "track" and track["shape"] == "ring" and len(track["spaces"]) == 40
    assert track["spaces"][MED]["tone"] == "brown" and track["spaces"][MED]["owner"] == 1
    assert track["spaces"][MED]["level"] == 2 and track["spaces"][BOARDWALK]["tone"] == "navy"
    assert track["spaces"][5]["icon"] == "cart"
    assert [t["at"] for t in track["tokens"]] == [3, 0]
    views = [p["view"] for p in sc["parts"]]
    assert views.count("kv") == 2 and views[1] == "dice"


def test_scene_buy_buttons_and_clickable_build_spaces():
    g, s = fresh()
    s = roll(g, s, "1-2")
    sc = g.scene(s, 0)
    buttons = sc["parts"][-1]
    assert buttons["view"] == "buttons"
    assert [c["action"] for c in buttons["choices"]] == ["buy", "skip"]
    assert buttons["choices"][0]["label"] == "Buy Baltic Ave for $60"
    assert sc["status"] == "You landed on Baltic Ave ($60). Buy it?"
    assert "buttons" not in [p["view"] for p in g.scene(s, 1)["parts"]]
    g, s = fresh()
    give(s, 0, [MED, BALTIC])
    s = roll(g, s, "1-2")
    sc = g.scene(s, 0)
    clickable = [i for i, sp in enumerate(sc["parts"][0]["spaces"]) if "action" in sp]
    assert clickable == [MED, BALTIC]
    assert sc["parts"][0]["spaces"][MED]["action"] == "build:1"


def test_jail_buttons_and_statuses():
    g, s = jailed()
    sc = g.scene(s, 0)
    assert [c["action"] for c in sc["parts"][-1]["choices"]] == ["pay", "wait"]
    assert "in jail" in json.dumps(sc)
    assert g.status(s, 1).endswith("is in jail and deciding")


def test_key_ignores_display_fields():
    g, s = fresh()
    t = g.copy_state(s)
    t.fresh, t.last, t.dice = True, (0, 5), (3, 4)
    assert g.key(s) == g.key(t)


# -------------------------------------------------------------------- simulation
def test_random_games_end_inside_the_limit_and_conserve_money():
    g = Monopoly()
    rng = random.Random(1)
    for _ in range(10):
        s = g.initial_state()
        while not g.is_terminal(s):
            a = g.sample_chance(s, rng) if g.current_player(s) == CHANCE \
                else rng.choice(g.legal_actions(s))
            s = g.apply_action(s, a)
            assert all(0 <= p < 40 for p in s.pos)
            assert all(h <= 4 for h in s.houses)
            assert all(s.houses[i] == 0 or s.owner[i] >= 0 for i in range(40))
        assert s.dead >= 0 or s.rounds >= 120


def test_buying_stacks_beat_random_and_good_stacks_are_close_to_each_other():
    g = Monopoly()
    for bot in ("tina", "bobby", "mona"):
        res = simulate(g, [g.make_policy(bot), g.make_policy("randy")], n=200, seed=3)
        assert res.wins(0) / 200 > 0.55                       # true rates are 0.63 to 0.69
    res = simulate(g, [g.make_policy("mona"), g.make_policy("bobby")], n=300, seed=3)
    assert 0.38 < res.wins(0) / 300 < 0.65                    # the dice own this board


def test_rounds_parameter_shortens_the_game():
    g = Monopoly(rounds=20)
    rets, steps, timeout = play_out(g, [g.make_policy("tina")] * 2, "short")
    assert not timeout and steps < 200


def test_insight_texts():
    g = Monopoly()
    assert "buying rule" in g.insight({"n": 100, "wins": [30, 70], "cards": ["builder"]})
    assert g.insight({"n": 100, "wins": [80, 20]}).startswith("A landslide")
    assert g.insight({"n": 100, "wins": [52, 48]}).startswith("Nearly even")
