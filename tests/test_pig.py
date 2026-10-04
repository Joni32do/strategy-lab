"""Pig: turn rules, the hold-at-20 arithmetic, rule cards, scenes, simulation."""

from __future__ import annotations

import json
import math
import random

import pytest

from strategy_lab.core import CHANCE
from strategy_lab.core.match import simulate
from strategy_lab.games.pig import HOLD, ROLL, Pig, PigState


def play(g, actions):
    s = g.initial_state()
    for a in actions:
        s = g.apply_action(s, a)
    return s


def rolled(g, s, die):
    """Roll once and resolve the chance node with ``die``."""
    s = g.apply_action(s, ROLL)
    assert g.current_player(s) == CHANCE
    return g.apply_action(s, die)


# --------------------------------------------------------------------------- rules
def test_die_adds_to_turn_total_and_the_roller_goes_on():
    g = Pig()
    s = rolled(g, g.initial_state(), 4)
    assert (s.total, s.turn, s.scores) == (4, 0, [0, 0])
    assert g.current_player(s) == 0
    s = rolled(g, s, 6)
    assert s.total == 10 and s.last == 6


def test_a_one_wipes_the_turn_total_and_passes_the_dice():
    g = Pig()
    s = play(g, [ROLL, 5, ROLL, 6, HOLD])        # player 0 banks 11
    assert s.scores == [11, 0] and s.turn == 1
    s = play(g, [ROLL, 5, ROLL, 6, ROLL, 1])     # player 0 rolls a 1 with 11 at risk
    assert s.scores == [0, 0] and s.turn == 1 and s.total == 0
    assert s.busted and s.lost == 11
    assert g.current_player(s) == 1


def test_hold_banks_and_passes_the_dice():
    g = Pig()
    s = play(g, [ROLL, 6, ROLL, 6, ROLL, 6, HOLD])
    assert s.scores == [18, 0] and s.turn == 1 and s.total == 0 and not s.busted


def test_hold_with_an_empty_turn_total_is_legal_and_changes_nothing_but_the_turn():
    g = Pig()
    s = g.apply_action(g.initial_state(), HOLD)
    assert s.scores == [0, 0] and s.turn == 1
    assert HOLD in g.legal_actions(g.initial_state())


def test_reaching_the_target_by_holding_wins_and_ends_the_game():
    g = Pig(target=20)
    s = g.initial_state()
    for _ in range(4):
        s = rolled(g, s, 5)                      # turn total 20, not yet banked
    assert not g.is_terminal(s)                  # no win until you hold
    s = g.apply_action(s, HOLD)
    assert g.is_terminal(s) and g.winner(s) == 0
    assert g.returns(s) == [1.0, -1.0]


def test_the_opponent_wins_with_their_own_hold():
    g = Pig(target=20)
    s = play(g, [HOLD])                          # player 0 passes
    for _ in range(4):
        s = rolled(g, s, 5)
    s = g.apply_action(s, HOLD)
    assert g.winner(s) == 1 and g.returns(s) == [-1.0, 1.0]


def test_chance_node_is_a_fair_die():
    g = Pig()
    s = g.apply_action(g.initial_state(), ROLL)
    outcomes = g.chance_outcomes(s)
    assert [a for a, _ in outcomes] == [1, 2, 3, 4, 5, 6]
    assert all(math.isclose(p, 1 / 6) for _, p in outcomes)
    info = g.chance_info(s, 3)
    assert math.isclose(info["entropy"], math.log2(6)) and info["outcomes"] == 6


def test_target_parameter_is_validated():
    assert Pig().p["target"] == 50
    assert Pig(target="75").p["target"] == 75       # JSON strings are coerced
    for bad in (19, 101):
        with pytest.raises(ValueError):
            Pig(target=bad)


def test_the_odds_hint_is_the_exact_average_change_of_one_more_roll():
    """(5/6)*4 - t/6 = (20 - t)/6: the arithmetic behind Hold at 20."""
    g = Pig()
    for t in (0, 6, 14, 20, 27):
        s = PigState(total=t)
        s = g.apply_action(s, ROLL)
        ev = 0.0
        for die, p in g.chance_outcomes(s):
            after = g.apply_action(s, die)
            gain = after.total - t               # a bust leaves total 0
            ev += p * gain
        assert math.isclose(ev, (20 - t) / 6, abs_tol=1e-9)
    assert "Average change +1.0" in g._roll_hint(PigState(total=14))
    assert "Average change +0.0" in g._roll_hint(PigState(total=20))
    assert "Average change -1.0" in g._roll_hint(PigState(total=26))


# ---------------------------------------------------------------------------- cards
def decide(g, card_ids, s, seed=0):
    pol = g.make_policy(cards=card_ids)
    return pol.decide(g, s, s.turn, random.Random(seed))


def test_hold_at_20_threshold():
    g = Pig()
    assert decide(g, ["hold20"], PigState(total=19))["action"] == ROLL
    assert decide(g, ["hold20"], PigState(total=20))["action"] == HOLD
    assert decide(g, ["hold10"], PigState(total=9))["action"] == ROLL
    assert decide(g, ["hold10"], PigState(total=10))["action"] == HOLD


def test_bank_the_win_beats_the_threshold_card_below_it():
    g = Pig(target=50)
    s = PigState(scores=[40, 10], total=10)
    assert decide(g, ["bank-win", "hold20"], s)["action"] == HOLD
    assert decide(g, ["bank-win", "hold20"], s)["card"] == "bank-win"
    assert decide(g, ["hold20"], s)["action"] == ROLL            # without it: keeps rolling


def test_never_hold_empty_vetoes_only_the_empty_hold():
    g = Pig()
    out = decide(g, ["never-hold-empty"], PigState(total=0))
    assert out["action"] == ROLL and out["vetoed"] == [("never-hold-empty", [HOLD])]
    # with something in hand the card has no opinion: a random legal action is played
    out = decide(g, ["never-hold-empty"], PigState(total=8))
    assert out["vetoed"] == [] and out["reason"] == "random"


def test_keep_pace_holds_earlier_when_leading_and_later_when_trailing():
    g = Pig(target=100)
    # equal scores: hold at 21
    assert decide(g, ["keep-pace"], PigState(scores=[10, 10], total=20))["action"] == ROLL
    assert decide(g, ["keep-pace"], PigState(scores=[10, 10], total=21))["action"] == HOLD
    # trailing by 16: hold at 23
    s = PigState(scores=[10, 26], total=22)
    assert decide(g, ["keep-pace"], s)["action"] == ROLL
    assert decide(g, ["keep-pace"], PigState(scores=[10, 26], total=23))["action"] == HOLD
    # leading by 16: hold at 19
    s = PigState(scores=[26, 10], total=19)
    assert decide(g, ["keep-pace"], s)["action"] == HOLD


def test_keep_pace_goes_all_in_near_the_end():
    g = Pig(target=100)
    s = PigState(scores=[40, 75], total=40)          # the opponent needs 25: race
    assert decide(g, ["keep-pace"], s)["action"] == ROLL
    s = PigState(scores=[40, 75], total=60)          # banking 60 wins
    assert decide(g, ["keep-pace"], s)["action"] == HOLD


def test_every_bot_names_known_cards():
    ids = {c.id for c in Pig.cards()}
    assert {"bank-win", "hold20", "hold10", "keep-pace", "never-hold-empty"} <= ids
    for b in Pig().bots:
        assert set(b.cards) <= ids


# --------------------------------------------------------------------------- scenes
def test_scene_has_dice_bars_and_buttons_for_the_mover():
    g = Pig()
    s = rolled(g, g.initial_state(), 5)
    sc = g.scene(s, 0)
    json.dumps(sc)
    views = [p["view"] for p in sc["parts"]]
    assert views == ["dice", "bars", "kv", "buttons"]
    assert sc["parts"][0]["fresh"] is True and sc["parts"][0]["dice"][0]["value"] == 5
    choices = {c["action"]: c for c in sc["parts"][3]["choices"]}
    assert set(choices) == {ROLL, HOLD}
    assert "1 in 6 to lose 5" in choices[ROLL]["sub"]
    assert "Bank 5" in choices[HOLD]["sub"]
    assert sc["status"] == "Roll or hold? Turn total 5"
    assert [p["name"] for p in sc["players"]] == ["You", "Player 2"]
    assert sc["players"][0]["active"] is True


def test_scene_hides_buttons_from_the_other_seat_and_after_the_end():
    g = Pig(target=20)
    s = rolled(g, g.initial_state(), 5)
    other = g.scene(s, 1)
    assert "buttons" not in [p["view"] for p in other["parts"]]
    s = g.initial_state()
    for _ in range(4):
        s = rolled(g, s, 5)
    s = g.apply_action(s, HOLD)
    done = g.scene(s, 0)
    assert "buttons" not in [p["view"] for p in done["parts"]]
    assert done["status"] == "You win: 20 to 0"
    assert g.status(s, 1) == "You lose: 0 to 20"


def test_status_after_a_bust_names_the_roller():
    g = Pig()
    s = play(g, [ROLL, 6, ROLL, 1])
    assert g.status(s, 0) == "You rolled a 1 and lost 6. Player 2 is about to roll"
    assert g.status(s, 1) == "Player 1 rolled a 1 and lost 6. Your turn: roll the die"


def test_captions_do_not_name_the_actor():
    g = Pig()
    s = g.initial_state()
    assert g.describe(s, ROLL, 0) == "starts rolling"
    s = g.apply_action(s, ROLL)
    assert g.describe_chance(s, 4) == "rolls a 4: turn total 4"
    assert g.describe_chance(s, 1) == "rolls a 1: pig out"
    s = rolled(g, g.initial_state(), 4)
    assert g.describe(s, HOLD, 0) == "holds and banks 4, now at 4"
    s = g.apply_action(s, ROLL)
    assert g.describe_chance(s, 1) == "rolls a 1 and loses 4: pig out"


def test_key_ignores_display_only_fields():
    g = Pig()
    a = PigState(scores=[3, 4], total=5, last=2, fresh=True)
    b = PigState(scores=[3, 4], total=5, last=6, fresh=False)
    assert g.key(a) == g.key(b)


# --------------------------------------------------------------------- simulation
def win_rate(g, a, b, n, seed=1):
    res = simulate(g, [g.make_policy(a), g.make_policy(b)], n=n, seed=seed)
    return res.wins(0) / n


def test_any_sensible_bot_crushes_random():
    g = Pig()
    for bot in ("tim", "tina", "kai"):
        assert win_rate(g, bot, "randy", 100) >= 0.9


def test_hold_at_20_beats_hold_at_10_and_keep_pace_beats_hold_at_20():
    g = Pig()
    assert win_rate(g, "tina", "tim", 400) > 0.58       # true rate is about 0.66
    assert win_rate(g, "kai", "tina", 600) > 0.52       # true rate is about 0.59
    assert win_rate(g, "kai", "tim", 400) > 0.58


def test_hold_at_20_is_the_best_fixed_threshold_per_turn():
    """Points banked per turn peak at a threshold of 20 or 21 (exact Markov chain)."""
    def turn_value(limit):
        # v[t]: expected points banked from turn total t under "hold at limit"
        v = {t: float(t) for t in range(limit, limit + 7)}
        for t in range(limit - 1, -1, -1):
            v[t] = (sum(v[t + d] for d in range(2, 7)) / 6)
        return v[0]
    best = max(range(5, 40), key=turn_value)
    assert best in (20, 21)
    assert turn_value(20) > turn_value(10) and turn_value(20) > turn_value(30)


def test_game_always_ends_with_random_play():
    g = Pig()
    for seed in range(20):
        res = simulate(g, [g.make_policy("randy")] * 2, n=1, seed=seed)
        assert not res.games[0].timeout


def test_insight_texts():
    g = Pig()
    base = {"n": 100, "wins": [60, 40], "bot": "tina"}
    assert "banking early" in g.insight(base).lower()
    assert "lost 60" in g.insight({**base, "wins": [40, 60]})
    assert g.insight({**base, "wins": [50, 50]}).startswith("Close")


# ------------------------------------------------------- the dice family helpers
def test_pair_outcomes_unordered_and_ordered():
    from strategy_lab.families.dice import DiceGame
    outs = dict(DiceGame.pair_outcomes())
    assert len(outs) == 21 and math.isclose(sum(outs.values()), 1.0)
    assert math.isclose(outs["4-4"], 1 / 36) and math.isclose(outs["2-5"], 2 / 36)
    assert "5-2" not in outs
    ordered = dict(DiceGame.pair_outcomes(ordered=True))
    assert len(ordered) == 36 and all(math.isclose(p, 1 / 36) for p in ordered.values())
    assert len(DiceGame.die_outcomes(10)) == 10
    assert DiceGame.parse_pair("3-5") == (3, 5) and DiceGame.is_double("6-6")
    assert not DiceGame.is_double("1-2")


def test_returns_from_scores_handles_ties_and_many_seats():
    g = Pig()
    assert g.returns_from_scores([5, 3]) == [1.0, -1.0]
    assert g.returns_from_scores([4, 4]) == [0.0, 0.0]
    assert g.returns_from_scores([9, 9, 1, 2]) == [0.0, 0.0, -1.0, -1.0]


def test_clone_is_independent_and_keeps_every_field():
    from strategy_lab.families.dice import clone
    s = PigState(scores=[3, 4], total=5, last=2)
    t = clone(s)
    t.scores[0] = 99
    assert s.scores == [3, 4] and t.total == 5 and t.last == 2 and t is not s
    nested = {"a": [[1, 2], [3]], "b": {1, 2}}
    copy = clone(nested)
    copy["a"][0].append(9)
    copy["b"].add(7)
    assert nested == {"a": [[1, 2], [3]], "b": {1, 2}}


def test_roll_and_move_advance_rejects_unknown_modes():
    from strategy_lab.families.dice import RollAndMoveGame
    with pytest.raises(ValueError):
        RollAndMoveGame.advance(0, 3, 10, "teleport")
