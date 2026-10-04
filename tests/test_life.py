"""The Game of Life: forks, paydays, milestones, chance nodes, retirement, cards, scene."""

from __future__ import annotations

import json
import math
import random

from strategy_lab.core import CHANCE
from strategy_lab.core.match import simulate
from strategy_lab.families.dice import RollAndMoveGame
from strategy_lab.games.life import CAREERS, Life, LifeState


def at(g=None, seat=0, pos=0, cash=0, career="server", college=False, insured=False,
       resolved=(), other_pos=0):
    """A seat that is about to spin, with its career chosen."""
    g = g or Life()
    s = LifeState()
    s.turn = seat
    for i in range(2):
        s.stage[i] = "spin"
        s.career[i] = career
    s.pos[seat] = pos
    s.cash[seat] = cash
    s.pos[1 - seat] = other_pos
    s.college[seat] = college
    s.insured[seat] = insured
    s.resolved[seat] = list(resolved)
    return g, g.settle(s)


def spin(g, s, v):
    assert g.current_player(s) == CHANCE and s.chance == "spin"
    return g.apply_action(s, v)


def decide(g, cards, s, seed=0):
    pol = g.make_policy(cards=cards)
    return pol.decide(g, s, s.turn, random.Random(seed))


# ----------------------------------------------------------------------- the start
def test_a_life_starts_at_the_fork_and_stays_with_one_seat_until_it_spins():
    g = Life()
    s = g.initial_state()
    assert s.stage == ["fork", "fork"] and g.current_player(s) == 0
    assert g.legal_actions(s) == ["college", "work"]
    s = g.apply_action(s, "college")
    assert s.cash[0] == -40 and s.college[0] and g.current_player(s) == 0
    assert g.legal_actions(s) == ["career:teacher", "career:lawyer", "career:doctor"]
    s = g.apply_action(s, "career:doctor")
    assert s.career[0] == "doctor" and g.current_player(s) == CHANCE and s.chance == "spin"
    s = spin(g, s, 3)
    assert s.pos[0] == 3 and s.turn == 1 and g.current_player(s) == 1   # now seat 1 chooses


def test_work_costs_nothing_and_offers_the_low_tier_careers():
    g = Life()
    s = g.apply_action(g.initial_state(), "work")
    assert s.cash[0] == 0 and not s.college[0]
    assert g.legal_actions(s) == ["career:server", "career:sales", "career:athlete"]


def test_the_spinner_is_a_ten_sided_chance_node():
    g, s = at()
    outs = g.chance_outcomes(s)
    assert [a for a, _ in outs] == list(range(1, 11))
    assert all(math.isclose(p, 0.1) for _, p in outs)
    assert math.isclose(g.chance_info(s, 4)["entropy"], math.log2(10))
    assert g.describe_chance(s, 7) == "spins a 7"


# ---------------------------------------------------------------------- paydays
def test_a_steady_payday_is_added_without_a_chance_node():
    g, s = at(pos=6, career="server")
    s = spin(g, s, 3)                                  # passes square 8
    assert s.cash[0] == 12 and s.pos[0] == 9
    g, s = at(pos=0, career="teacher", college=True)
    s = spin(g, s, 8)                                  # lands on a payday
    assert s.cash[0] == 20


def test_a_risky_career_pays_through_a_chance_node_that_averages_to_the_salary():
    g, s = at(pos=6, career="athlete")
    s = spin(g, s, 3)
    assert g.current_player(s) == CHANCE and s.chance == "payday"
    outs = g.chance_outcomes(s)
    assert len(outs) == 29 and math.isclose(sum(p for _, p in outs), 1.0)
    pays = [CAREERS["athlete"].pay + v - 14 for v, _ in outs]
    assert min(pays) == 8 and max(pays) == 36 and sum(pays) / len(pays) == 22
    s = g.apply_action(s, 0)
    assert s.cash[0] == 8 and s.turn == 1
    assert g.describe_chance(g.apply_action(at(pos=6, career="athlete")[1], 3), 14) == \
        "collects a payday of $22k"


def test_no_career_no_payday():
    g, s = at(pos=6, career="")
    s = spin(g, s, 3)
    assert s.cash[0] == 0


# --------------------------------------------------------------------- milestones
def test_passing_the_insurance_square_triggers_the_decision_after_the_move():
    g, s = at(pos=9, career="server")
    s = spin(g, s, 6)                                   # 15: passed 12
    assert s.pos[0] == 15 and s.stage[0] == "insure" and g.current_player(s) == 0
    assert g.legal_actions(s) == ["buy-insurance", "no-insurance"]
    s2 = g.apply_action(s, "buy-insurance")
    assert s2.insured[0] and s2.cash[0] == -15 and s2.turn == 1
    assert "ins" in s2.resolved[0] and s2.stage[0] == "spin"
    s3 = g.apply_action(s, "no-insurance")
    assert not s3.insured[0] and s3.turn == 1


def test_hazards_are_a_forty_percent_chance_unless_insured():
    g, s = at(pos=16, career="", resolved=["ins"])
    s = spin(g, s, 5)                                   # passes 20
    assert s.chance == "hazard"
    outs = dict(g.chance_outcomes(s))
    assert math.isclose(outs[1], 0.4) and math.isclose(outs[0], 0.6)
    assert g.apply_action(s, 1).cash[0] == -40 and g.apply_action(s, 0).cash[0] == 0
    assert g.action_label(s, 1) == "accident" and g.action_label(s, 0) == "safe"
    g, s = at(pos=16, career="", insured=True, resolved=["ins"])
    s = spin(g, s, 5)
    assert s.turn == 1 and s.chance == "spin" and s.cash[0] == 0     # waived: seat 1 spins


def test_marriage_and_baby_gifts():
    g, s = at(pos=28, career="", resolved=["ins", "g0"])
    s = spin(g, s, 3)
    assert s.cash[0] == 20
    g, s = at(pos=48, career="", resolved=["ins", "g0", "g1"], insured=True)
    s = spin(g, s, 4)
    assert s.cash[0] == 12


def test_stock_market_bet_is_an_even_chance_of_plus_40_or_minus_30():
    g, s = at(pos=22, career="", resolved=["ins"], insured=True)
    s = spin(g, s, 4)                                   # 26: passed 24
    assert s.stage[0] == "gamble" and g.legal_actions(s) == ["bet", "no-bet"]
    bet = g.apply_action(s, "bet")
    assert g.current_player(bet) == CHANCE and bet.chance == "gamble"   # the outcome is still due
    outs = dict(g.chance_outcomes(bet))
    assert outs == {1: 0.5, 0: 0.5}
    win, lose = g.apply_action(bet, 1), g.apply_action(bet, 0)
    assert win.cash[0] == 40 and lose.cash[0] == -30
    assert win.turn == 1 and "g0" in win.resolved[0]
    assert g.describe_chance(bet, 1) == "wins big at the market: +$40k"
    skip = g.apply_action(s, "no-bet")
    assert skip.cash[0] == 0 and skip.turn == 1


def test_the_second_market_stop_is_at_square_40():
    g, s = at(pos=38, career="", resolved=["ins", "g0"], insured=True)
    s = spin(g, s, 4)
    assert s.stage[0] == "gamble" and "g1" not in s.resolved[0]
    s = g.apply_action(s, "no-bet")
    assert "g1" in s.resolved[0]


def test_the_road_ends_at_60_and_retirement_is_a_choice():
    g, s = at(pos=57, career="", resolved=["ins", "g0", "g1"], insured=True)
    s = spin(g, s, 10)
    assert s.pos[0] == 60 and s.stage[0] == "retire"
    assert g.legal_actions(s) == ["country", "estates"]
    c = g.apply_action(s, "country")
    assert c.cash[0] == 100 and c.stage[0] == "done" and c.turn == 1
    e = g.apply_action(s, "estates")
    assert e.chance == "estates" and g.current_player(e) == CHANCE
    outs = g.chance_outcomes(e)
    assert [a for a, _ in outs] == list(range(1, 11))
    assert g.apply_action(e, 7).cash[0] == 7 * 24 and g.apply_action(e, 7).stage[0] == "done"
    assert g.describe_chance(e, 7) == "cashes out Millionaire Estates after a spin of 7: +$168k"


def test_the_estates_gamble_is_better_on_average_than_the_sure_thing():
    assert sum(range(1, 11)) / 10 * 24 == 132 > 100


# ------------------------------------------------------------------------ the end
def test_the_game_ends_when_both_retire_and_more_cash_wins():
    g, s = at(pos=57, career="", resolved=["ins", "g0", "g1"], insured=True)
    s.pos[1] = 60
    s.stage[1] = "retire"
    s.cash = [50, 100]
    s = spin(g, s, 10)                                  # seat 0 reaches 60
    assert s.stage[0] == "retire" and s.turn == 0
    s = g.apply_action(s, "country")                    # seat 0: 150 total
    assert s.turn == 1 and g.current_player(s) == 1
    s = g.apply_action(s, "country")                    # seat 1: 200 total
    assert g.is_terminal(s) and g.winner(s) == 1
    assert g.returns(s) == [-1.0, 1.0]
    assert g.status(s, 0) == "You lose: $150k against $200k"
    assert g.status(s, 1) == "You win with $200k"


def test_ties_are_draws_and_timeouts_go_to_the_richer():
    g = Life()
    s = LifeState()
    s.cash = [10, 10]
    assert g.winner(s) is None and g.timeout_returns(s) == [0.0, 0.0]
    s.cash = [10, 30]
    assert g.timeout_returns(s) == [-1.0, 1.0]


def test_a_finished_seat_is_skipped_and_the_other_keeps_going():
    g, s = at(seat=0, pos=57, career="", resolved=["ins", "g0", "g1"], insured=True)
    s.stage[1] = "done"
    s = spin(g, s, 10)
    s = g.apply_action(s, "country")
    assert s.stage[0] == "done" and g.is_terminal(s)
    g, s = at(seat=1, pos=0)
    s.stage[0] = "done"
    s = spin(g, s, 2)
    assert s.turn == 1 and g.current_player(s) == CHANCE      # seat 1 spins again


# -------------------------------------------------------------------------- cards
def test_career_cards():
    g = Life()
    s = g.apply_action(g.initial_state(), "college")
    assert decide(g, ["big-salary"], s)["action"] == "career:doctor"
    assert decide(g, ["steady"], s)["action"] == "career:teacher"
    s = g.apply_action(g.initial_state(), "work")
    assert decide(g, ["big-salary"], s)["action"] == "career:athlete"
    assert decide(g, ["steady"], s)["action"] == "career:server"
    assert decide(g, ["college"], g.initial_state())["action"] == "college"


def test_insurance_market_and_retirement_cards():
    g, s = at(pos=9)
    s = spin(g, s, 6)
    assert decide(g, ["insured"], s)["action"] == "buy-insurance"
    g, s = at(pos=22, resolved=["ins"], insured=True)
    s = spin(g, s, 4)
    assert decide(g, ["high-roller"], s)["action"] == "bet"
    out = decide(g, ["safe", "high-roller"], s)
    assert out["action"] == "no-bet" and out["vetoed"] == [("safe", ["bet"])]
    g, s = at(pos=57, resolved=["ins", "g0", "g1"], insured=True)
    s = spin(g, s, 10)
    assert decide(g, ["high-roller"], s)["action"] == "estates"
    assert decide(g, ["safe"], s)["action"] == "country"


def test_cards_and_bots_are_consistent():
    ids = {c.id for c in Life.cards()}
    assert ids == {"college", "big-salary", "steady", "insured", "high-roller", "safe"}
    for b in Life().bots:
        assert set(b.cards) <= ids


# -------------------------------------------------------------------------- scene
def test_scene_has_a_serpentine_road_with_milestones_tokens_and_panels():
    g, s = at(pos=9)
    s = spin(g, s, 6)                                   # the insurance decision of seat 0
    sc = g.scene(s, 0)
    json.dumps(sc)
    track = sc["parts"][0]
    assert track["view"] == "track" and track["shape"] == "serpentine"
    assert len(track["spaces"]) == 61
    assert track["spaces"][12]["icon"] == "shield" and track["spaces"][24]["icon"] == "slot"
    assert track["spaces"][20]["tone"] == "bad" and track["spaces"][16]["tone"] == "good"
    assert track["spaces"][60]["tone"] == "goal"
    assert {t["owner"]: t["at"] for t in track["tokens"]} == {0: 15, 1: 0}
    kvs = [p for p in sc["parts"] if p["view"] == "kv"]
    assert len(kvs) == 2 and kvs[0]["items"][0] == ["Cash", "$0k"]
    buttons = sc["parts"][-1]
    assert [c["action"] for c in buttons["choices"]] == ["buy-insurance", "no-insurance"]
    assert "chance 40%" in buttons["choices"][0]["sub"]
    assert sc["status"] == "Buy insurance?"
    assert "buttons" not in [p["view"] for p in g.scene(s, 1)["parts"]]


def test_scene_career_buttons_name_the_pay_and_the_swing():
    g = Life()
    s = g.apply_action(g.initial_state(), "work")
    buttons = g.scene(s, 0)["parts"][-1]
    labels = [c["label"] for c in buttons["choices"]]
    assert labels[0] == "Server ($12k per payday)"
    assert buttons["choices"][0]["sub"] == "$12k per payday, always the same."
    assert "plus or minus $14k" in buttons["choices"][2]["sub"]


def test_key_ignores_display_fields_and_copy_is_independent():
    g, s = at(pos=9)
    t = g.copy_state(s)
    t.fresh = True
    t.spin = 5
    assert g.key(s) == g.key(t)
    t.resolved[0].append("ins")
    t.cash[0] = 99
    assert s.resolved[0] == [] and s.cash[0] == 0


# ---------------------------------------------------------------------- simulation
def test_random_lives_always_end():
    g = Life()
    rng = random.Random(2)
    for _ in range(30):
        s = g.initial_state()
        steps = 0
        while not g.is_terminal(s):
            a = g.sample_chance(s, rng) if g.current_player(s) == CHANCE \
                else rng.choice(g.legal_actions(s))
            s = g.apply_action(s, a)
            steps += 1
            assert steps < 400
        assert s.stage == ["done", "done"] and s.pos[0] <= 60


def test_the_advance_helper_stops_at_the_end_of_the_road():
    step = RollAndMoveGame.advance(57, 10, 60, "stop")
    assert step.dest == 60 and step.path == (58, 59, 60)


def win_rate(g, a, b, n, seed=1):
    return simulate(g, [g.make_policy(a), g.make_policy(b)], n=n, seed=seed).wins(0) / n


def test_income_beats_safety_and_a_bold_stack_beats_the_careful_one():
    g = Life()
    assert win_rate(g, "clara", "stan", 200) > 0.9            # about 0.99
    assert win_rate(g, "clara", "randy", 300) > 0.7           # about 0.80
    assert win_rate(g, "vera", "clara", 400) > 0.5            # about 0.58: the bets pay off
    assert win_rate(g, "stan", "randy", 300) < 0.4            # about 0.24: safety is not free


def test_insight_texts():
    g = Life()
    base = {"n": 100, "wins": [30, 70]}
    assert "Net worth is mostly salary" in g.insight({**base, "cards": ["insured"]})
    assert "Safety costs money" in g.insight({**base, "cards": ["college", "safe"]})
    assert g.insight({"n": 100, "wins": [70, 30], "cards": ["college"]}).startswith("Convincing")
    assert g.insight({"n": 100, "wins": [52, 48], "cards": ["college"]}).startswith("Nearly even")
