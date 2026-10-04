"""The matrix-game family: the math of tables, hidden commits, shared cards."""

from __future__ import annotations

import json
import math
import random

import numpy as np
import pytest

from strategy_lab.core import Seat, Session
from strategy_lab.core.match import simulate
from strategy_lab.families.matrix import (
    best_responses, dominated_by, entropy_bits, exploitability, nash_gap, pure_equilibria,
    solve_2x2, support_enumeration, zero_sum_value,
)
from strategy_lab.games.matching_pennies import MatchingPennies
from strategy_lab.games.prisoners_dilemma import PrisonersDilemma
from strategy_lab.games.rps import RockPaperScissors
from strategy_lab.games.stag_hunt import StagHunt

GAMES = [RockPaperScissors, MatchingPennies, PrisonersDilemma, StagHunt]
RPS = np.array([[0, -1, 1], [1, 0, -1], [-1, 1, 0]], dtype=float)


def play(g, actions):
    s = g.initial_state()
    for a in actions:
        s = g.apply_action(s, a)
    return s


# ------------------------------------------------------------------ the math
def test_best_responses_keep_ties():
    assert best_responses([1.0, 3.0, 3.0]) == [1, 2]
    assert best_responses([0.0, -1.0]) == [0]


def test_rps_has_only_the_uniform_equilibrium():
    eqs = support_enumeration(RPS, -RPS)
    assert len(eqs) == 1
    assert np.allclose(eqs[0].row, 1 / 3) and np.allclose(eqs[0].col, 1 / 3)
    assert pure_equilibria(RPS, -RPS) == []


def test_closed_form_matches_support_enumeration_on_2x2():
    A = np.array([[1.0, -1.0], [-1.0, 1.0]])
    p, q = solve_2x2(A, -A)
    assert np.allclose(p, [0.5, 0.5]) and np.allclose(q, [0.5, 0.5])
    sh = StagHunt()
    p, q = solve_2x2(sh.A, sh.B)
    mixed = [e for e in support_enumeration(sh.A, sh.B) if not e.pure][0]
    assert np.allclose(p, mixed.row) and np.allclose(p, [0.75, 0.25])


def test_no_mixed_equilibrium_in_a_dominance_game():
    pd = PrisonersDilemma()
    assert solve_2x2(pd.A, pd.B) is None


def test_zero_sum_value_exploitability_and_gap():
    assert zero_sum_value(RPS) == pytest.approx(0.0)
    assert exploitability(RPS, np.ones(3) / 3) == pytest.approx(0.0, abs=1e-9)
    assert exploitability(RPS, np.array([1.0, 0.0, 0.0])) == pytest.approx(1.0)
    u = np.ones(3) / 3
    assert nash_gap(RPS, -RPS, u, u) == pytest.approx(0.0, abs=1e-9)
    assert nash_gap(RPS, -RPS, np.array([1.0, 0, 0]), u) > 0.5


def test_dominance_and_entropy():
    pd = PrisonersDilemma()
    U = pd.utility_matrix(0)
    assert dominated_by(U, 0, 1) and not dominated_by(U, 1, 0)
    assert entropy_bits([0.5, 0.5]) == pytest.approx(1.0)
    assert entropy_bits([1.0, 0.0]) == 0.0
    assert entropy_bits(np.ones(3) / 3) == pytest.approx(math.log2(3))


# --------------------------------------------------------------- the family
def test_lineage_and_family():
    assert RockPaperScissors.lineage() == ["Game", "MatrixGame", "RockPaperScissors"]
    assert StagHunt.family()["id"] == "matrix"
    assert all(g.simultaneous and not g.perfect_information for g in GAMES)
    ids = {c.id for c in RockPaperScissors.cards()}
    assert {"copy", "hunt", "mix", "wsls", "outthink"} <= ids


def test_a_round_is_two_hidden_sequential_moves():
    g = RockPaperScissors(rounds=2)
    s = g.initial_state()
    assert g.current_player(s) == 0
    s = g.apply_action(s, 1)                       # seat 0 commits paper
    assert g.current_player(s) == 1 and s.rounds == [] and s.scores == [0, 0]
    s = g.apply_action(s, 0)                       # seat 1 commits rock: paper wins
    assert s.rounds == [(1, 0)] and s.scores == [1, -1] and g.current_player(s) == 0
    s = play(g, [1, 0, 2, 2])
    assert g.is_terminal(s) and g.returns(s) == [1.0, -1.0]


def test_returns_are_cumulative_payoffs():
    g = PrisonersDilemma(rounds=3)
    s = play(g, [0, 0, 1, 0, 1, 1])                # CC, DC, DD
    assert g.returns(s) == [3 + 5 + 1, 3 + 0 + 1]


def test_first_commit_is_private_and_second_reveals_the_round():
    g = RockPaperScissors()
    s0 = g.initial_state()
    s1 = g.apply_action(s0, 2)
    assert g.privacy(s0, 2, 0) == (0,)
    assert g.privacy(s1, 0, 1) is None
    assert "Scissors" not in g.describe_hidden(s0, 2, 0)
    caption = g.describe(s1, 0, 1)
    assert "Rock" in caption and "Scissors" in caption and "beats" in caption


def test_session_log_hides_the_first_commit_from_the_other_seat():
    g = RockPaperScissors(rounds=1)
    sess = Session(g, [Seat("bot", "rocky"), Seat("human")], 4)
    sess.advance()                                   # the bot commits first
    step = sess.steps[0]
    seen_by_human = step.to_json(0, viewer=1)
    assert seen_by_human["hidden"] is True and "a" not in seen_by_human
    assert "label" not in seen_by_human
    assert step.to_json(0, viewer=0)["a"] == 0       # the bot's own seat may see it
    sess.act(1)
    assert sess.terminal
    assert sess.steps[1].to_json(1, viewer=0)["text"]   # the reveal is public


def test_observation_and_scene_never_leak_the_pending_commit():
    g = RockPaperScissors()
    rock, paper = play(g, [0]), play(g, [1])
    assert g.observation(rock, 1) == g.observation(paper, 1)
    assert g.observation(rock, 0) != g.observation(paper, 0)    # you know your own commit
    assert g.scene(rock, 1) == g.scene(paper, 1)
    assert g.scene(rock, None) == g.scene(paper, None)
    json.dumps(g.scene(rock, 1))


def test_scene_is_from_the_viewers_side_and_rows_are_clickable_on_your_turn():
    g = PrisonersDilemma()
    s = g.initial_state()
    mine = g.scene(s, 0)["parts"][0]
    assert mine["rowActions"] == [0, 1] and mine["rowPlayer"] == 0
    waiting = g.scene(s, 1)["parts"][0]
    assert "rowActions" not in waiting
    # after seat 0 commits it is seat 1's turn: payoffs are transposed to its view
    s = g.apply_action(s, 1)                                   # seat 0 defects
    view = g.scene(s, 1)["parts"][0]
    assert view["rowActions"] == [0, 1] and view["rowPlayer"] == 1
    # seat 1 cooperating (row 0) against a defector (col 1): sucker payoff 0, and 5 for them
    assert view["payoffs"][0][1] == [0, 5]
    assert "rowActions" not in g.scene(s, 0)["parts"][0]


def test_scene_highlights_the_last_round_and_lists_history():
    g = RockPaperScissors()
    s = play(g, [0, 1, 2, 2])
    part = g.scene(s, 0)["parts"][0]
    assert part["highlight"] == [2, 2] and part["history"] == [[0, 1]]
    flipped = g.scene(s, 1)["parts"][0]
    assert flipped["history"] == [[1, 0]]


def test_status_headlines():
    g = MatchingPennies(rounds=1)
    s = g.initial_state()
    assert "choose your move" in g.status(s, 0)
    assert "waiting" in g.status(s, 1)
    assert "Game over" in g.status(play(g, [0, 0]), 0)


# ------------------------------------------------------- bots read only history
@pytest.mark.parametrize("cls", GAMES, ids=lambda c: c.id)
def test_bots_ignore_the_other_seats_pending_commit(cls):
    g = cls(rounds=20)
    s = g.initial_state()
    rng = random.Random(1)
    for _ in range(5):                                # a few revealed rounds
        s = g.apply_action(s, rng.choice(g.legal_actions(s)))
        s = g.apply_action(s, rng.choice(g.legal_actions(s)))
    for bot in g.bots:
        policy = g.make_policy(bot.id)
        picks = set()
        for commit in g.legal_actions(s):             # seat 1 faces every possible commit
            pending = g.apply_action(s, commit)
            picks.add(policy.act(g, pending, 1, random.Random(7)))
        assert len(picks) == 1, f"{bot.id} reacted to a hidden commit"


def test_hunter_punishes_a_predictable_player():
    g = RockPaperScissors()
    always_rock = g.make_policy(cards=["rock"])
    res = simulate(g, [always_rock, g.make_policy("hank")], n=20, seed=1)
    assert res.mean_return(0) < -10


def test_hunter_cannot_beat_the_equilibrium_mix():
    g = RockPaperScissors()
    res = simulate(g, [g.make_policy("nina"), g.make_policy("hank")], n=300, seed=2)
    assert abs(res.mean_return(0)) < 1.0


def test_outthink_card_beats_the_hunter():
    g = RockPaperScissors()
    res = simulate(g, [g.make_policy(cards=["outthink"]), g.make_policy("hank")], n=50, seed=3)
    assert res.wins(0) >= 40


def test_copy_card_repeats_the_last_revealed_move():
    g = RockPaperScissors()
    s = play(g, [1, 2])                               # seat 0 paper, seat 1 scissors
    card = g.card("copy")
    assert card.fn(g, s, [0, 1, 2], 0, random.Random(0)) == 2   # seat 0 copies scissors
    assert card.fn(g, s, [0, 1, 2], 1, random.Random(0)) == 1
    assert card.fn(g, g.initial_state(), [0, 1, 2], 0, random.Random(0)) is None
