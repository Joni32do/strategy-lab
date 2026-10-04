"""OpenSpiel-backed games: chess, backgammon, Kuhn poker, Skat, Doppelkopf.

Adapter-level checks: replay determinism, hidden information really hidden
(scenes, observations and the move log), action labels, and bot sanity.
The generic contract is covered by ``test_conformance.py``.
"""

from __future__ import annotations

import json
import random

import pyspiel
import pytest

from strategy_lab.core import CHANCE, Seat, Session
from strategy_lab.core.match import simulate
from strategy_lab.families.external import MCTSPolicy, SpielGame
from strategy_lab.games.backgammon import Backgammon, decode_board, parse_steps, pip_counts
from strategy_lab.games.chess import Chess
from strategy_lab.games.doppelkopf import Doppelkopf
from strategy_lab.games.kuhn_poker import KuhnNashPolicy, KuhnPoker, nash_bet_probabilities
from strategy_lab.games.skat import Skat

SPIEL_GAMES = [Chess, Backgammon, KuhnPoker, Skat, Doppelkopf]


def bots(game, bot="random"):
    return [Seat("bot", bot) for _ in range(game.num_players)]


def play(game, bot="random", seed=1, steps=None):
    sess = Session(game, bots(game, bot), seed)
    n = 0
    while not sess.terminal and (steps is None or n < steps):
        sess.step()
        n += 1
    return sess


# --------------------------------------------------------------------------- #
# Shared adapter behavior
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cls", SPIEL_GAMES, ids=lambda c: c.id)
def test_family_and_flags(cls):
    g = cls()
    assert issubclass(cls, SpielGame)
    assert g.family()["base"] in ("SpielGame", "CardTableGame", "TrickTakingGame")
    engine = pyspiel.load_game(cls.spiel_name)
    perfect = engine.get_type().information == pyspiel.GameType.Information.PERFECT_INFORMATION
    assert g.perfect_information == perfect
    assert g.num_players == engine.num_players()


@pytest.mark.parametrize("cls", SPIEL_GAMES, ids=lambda c: c.id)
def test_replay_is_deterministic(cls):
    g = cls()
    sess = play(g, seed=5, steps=70)
    again = Session(g, sess.seats, 5, sess.log, strict=True)
    assert g.key(again.state) == g.key(sess.state)
    # copying must not alias engine state
    s = sess.state
    c = g.copy_state(s)
    if not g.is_terminal(c) and g.current_player(c) != CHANCE:
        g.move(c, g.legal_actions(c)[0])
        assert g.key(c) != g.key(s)


@pytest.mark.parametrize("cls", SPIEL_GAMES, ids=lambda c: c.id)
def test_labels_are_text_and_ascii_free_of_none(cls):
    g = cls()
    sess = play(g, seed=2, steps=60)
    for step in sess.steps:
        assert step.text and step.label
    s = sess.state
    if not g.is_terminal(s) and g.current_player(s) != CHANCE:
        assert all(isinstance(g.action_label(s, a), str) and g.action_label(s, a)
                   for a in g.legal_actions(s))


def test_mcts_policy_is_deterministic_and_legal():
    g = Chess()
    s = g.initial_state()
    pol = MCTSPolicy(20, name="t")
    a1 = pol.act(g, s, 0, random.Random(4))
    a2 = pol.act(g, s, 0, random.Random(4))
    assert a1 == a2 and a1 in g.legal_actions(s)
    assert "visit_share" in pol.trace(g, s, 0)


# --------------------------------------------------------------------------- #
# Chess
# --------------------------------------------------------------------------- #
def test_chess_scene_and_labels():
    g = Chess()
    s = g.initial_state()
    labels = {g.action_label(s, a) for a in g.legal_actions(s)}
    assert {"e4", "Nf3", "a3"} <= labels and len(labels) == 20
    grid = g.scene(s, 0)["parts"][0]
    assert (grid["rows"], grid["cols"], grid["style"]) == (8, 8, "checker")
    assert grid["cells"][0]["pieces"][0] == {"owner": 1, "shape": "glyph", "glyph": "r"}
    assert grid["cells"][60]["pieces"][0]["glyph"] == "K"       # e1
    e2 = grid["cells"][52]
    assert {m["label"] for m in e2["moves"]} == {"e3", "e4"}
    assert g.current_player(s) == 0 and g.seat_label(0) == "White"


def test_chess_last_move_highlight_and_mate():
    g = Chess()
    s = g.initial_state()
    for san in ("f3", "e5", "g4", "Qh4#"):
        a = next(a for a in g.legal_actions(s) if g.action_label(s, a) == san)
        s = g.apply_action(s, a)
    assert g.is_terminal(s) and g.returns(s) == [-1.0, 1.0]
    assert g.status(s, 1).startswith("Checkmate")
    cells = g.scene(s, 1)["parts"][0]["cells"]
    assert sum(1 for c in cells if c.get("tone") == "last") == 2
    assert sum(1 for c in cells if c.get("tone") == "bad") == 1  # the mated king


def test_chess_material_heuristic_and_bots_finish_mate_in_one():
    g = Chess()
    s = g.initial_state()
    assert g.heuristic(s, 0) == 0
    s = g.initial_state()
    for san in ("f3", "e5", "g4"):
        a = next(a for a in g.legal_actions(s) if g.action_label(s, a) == san)
        s = g.apply_action(s, a)
    for bot in ("greta", "sven", "maxine"):
        a = g.make_policy(bot).act(g, s, 1, random.Random(0))
        assert g.action_label(s, a) == "Qh4#", bot


# --------------------------------------------------------------------------- #
# Backgammon
# --------------------------------------------------------------------------- #
def test_backgammon_decode_start_position():
    g = Backgammon()
    s = g.initial_state()
    info = decode_board(s)
    assert [sum(side) for side in info["board"]] == [15, 15]
    assert pip_counts(info) == [167, 167]
    assert info["bar"] == [0, 0] and info["off"] == [0, 0]
    assert len(g.chance_outcomes(s)) == 30      # opening roll decides who starts


def test_backgammon_scene_and_chance_labels():
    g = Backgammon()
    s = g.apply_action(g.initial_state(), 2)    # X starts with 1-3
    assert g.action_label(g.initial_state(), 2) == "1-3"
    part = g.scene(s, 0)["parts"][0]
    assert part["view"] == "backgammon" and len(part["points"]) == 24
    assert sum(p["n"] for p in part["points"] if p.get("owner") == 0) == 15
    assert part["moves"] and all(m["steps"] for m in part["moves"])
    assert any(p["view"] == "dice" for p in g.scene(s, 0)["parts"])
    assert g.scene(s, 1)["parts"][0]["moves"] == []          # not your turn: nothing to click


def test_backgammon_parse_steps():
    assert parse_steps("24/21*/20 6/5(2)", 0) == [
        {"from": 0, "to": 3, "hit": True}, {"from": 3, "to": 4, "hit": False},
        {"from": 18, "to": 19, "hit": False}, {"from": 18, "to": 19, "hit": False}]
    assert parse_steps("Bar/20 6/Off", 1) == [
        {"from": "bar", "to": 19, "hit": False}, {"from": 5, "to": "off", "hit": False}]
    assert parse_steps("Pass", 0) == []


def test_backgammon_variant_params_reach_the_engine():
    g = Backgammon(scoring_type="enable_gammons", hyper_backgammon=True)
    assert g.engine.get_parameters()["hyper_backgammon"] is True
    sess = play(g, "pete", seed=3)
    assert sess.terminal


def test_backgammon_pete_beats_random():
    g = Backgammon()
    res = simulate(g, [g.make_policy("pete"), g.make_policy("randy")], n=30, seed=1)
    assert res.wins(0) > res.wins(1)


# --------------------------------------------------------------------------- #
# Kuhn poker
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("alpha", [0.0, 1 / 6, 1 / 3])
def test_kuhn_nash_family_has_zero_exploitability(alpha):
    game = pyspiel.load_game("kuhn_poker")
    probs = nash_bet_probabilities(alpha)
    policy = pyspiel.TabularPolicy({k: [(0, 1 - p), (1, p)] for k, p in probs.items()})
    assert pyspiel.exploitability(game, policy) < 1e-9


def test_kuhn_nash_value_and_exploitation():
    g = KuhnPoker()
    nora = g.make_policy("nora")
    res = simulate(g, [nora, nora], n=3000, seed=2)
    assert abs(res.mean_return(0)) < 0.08
    # the equilibrium is not beaten by a bot that always bets, and beats it
    bettina = g.make_policy("bettina")
    res = simulate(g, [nora, bettina], n=3000, seed=3)
    assert res.mean_return(0) > 0.03
    with pytest.raises(ValueError):
        nash_bet_probabilities(0.5)


def test_kuhn_table_hides_the_opponent_card_until_showdown():
    g = KuhnPoker()
    s = g.initial_state()
    for a in (2, 1):                                  # seat 0: K, seat 1: Q
        s = g.apply_action(s, a)
    for viewer, own, other in ((0, "K", "Q"), (1, "Q", "K")):
        table = g.scene(s, viewer)["parts"][0]
        assert [c["rank"] for c in table["hand"]] == [own]
        assert "trick" not in table and other not in json.dumps(table)
    assert g.observation(s, 0) != g.observation(s, 1)
    # a fold keeps the card hidden, a showdown shows it
    folded = g.apply_action(g.apply_action(s, 1), 0)           # bet, fold
    assert g.is_terminal(folded) and "trick" not in g.scene(folded, 0)["parts"][0]
    shown = g.apply_action(g.apply_action(s, 1), 1)            # bet, call
    trick = g.scene(shown, 0)["parts"][0]["trick"]
    assert sorted(t["card"]["rank"] for t in trick) == ["K", "Q"]
    assert g.returns(shown) == [2.0, -2.0]


def test_kuhn_scene_is_the_same_in_every_world_the_seat_considers_possible():
    g = KuhnPoker()
    s = g.apply_action(g.apply_action(g.initial_state(), 0), 1)    # J vs Q
    t = g.apply_action(g.apply_action(g.initial_state(), 0), 2)    # J vs K
    assert g.observation(s, 0) == g.observation(t, 0)
    assert json.dumps(g.scene(s, 0)) == json.dumps(g.scene(t, 0))
    assert g.observation(s, 1) != g.observation(t, 1)


def test_kuhn_mcts_never_peeks_at_the_hidden_card():
    g = KuhnPoker()
    pol = MCTSPolicy(60, worlds=4, name="t")
    for own in (0, 1, 2):
        picks = set()
        for other in (c for c in range(3) if c != own):
            s = g.apply_action(g.apply_action(g.initial_state(), own), other)
            picks.add(pol.act(g, s, 0, random.Random(9)))
        assert len(picks) == 1, f"decision with card {own} changed with the opponent's card"


def test_kuhn_cards_bots_and_labels():
    g = KuhnPoker()
    s = g.apply_action(g.apply_action(g.initial_state(), 2), 0)
    assert {g.action_label(s, a) for a in g.legal_actions(s)} == {"Check", "Bet"}
    s2 = g.apply_action(s, 1)
    assert {g.action_label(s2, a) for a in g.legal_actions(s2)} == {"Call", "Fold"}
    hans = g.make_policy("hans")
    rng = random.Random(0)
    assert hans.act(g, s, 0, rng) == 1                    # King bets
    j = g.apply_action(g.apply_action(g.initial_state(), 0), 2)
    assert hans.act(g, j, 0, rng) == 0                    # Jack checks
    assert KuhnNashPolicy().trace(g, j, 0)["info_state"] == "0"


def test_kuhn_deal_is_private_to_the_receiver():
    g = KuhnPoker()
    sess = Session(g, [Seat("human"), Seat("bot", "nora")], 3)
    sess.advance()
    first, second = sess.steps[0], sess.steps[1]
    assert first.private == (0,) and second.private == (1,)
    mine = first.to_json(0, viewer=0)
    other = first.to_json(0, viewer=1)
    assert mine["text"] == "deals the " + mine["text"].split("the ")[1] and "a" in mine
    assert other["hidden"] is True and "a" not in other and "Jack" not in other["text"] \
        and "Queen" not in other["text"] and "King" not in other["text"]
    assert other["text"] == "deals a card to Player 1"
    assert first.to_json(0, viewer=None)["text"] == mine["text"]     # a spectator sees all


# --------------------------------------------------------------------------- #
# Skat
# --------------------------------------------------------------------------- #
def dealt_skat(seed):
    g = Skat()
    sess = Session(g, [Seat("human"), Seat("bot", "heidi"), Seat("bot", "heidi")], seed)
    sess.advance()
    return g, sess


def swap_hands(history, g, a, b):
    """The same deal with the cards of seats ``a`` and ``b`` exchanged."""
    from strategy_lab.games.skat import DEAL_ORDER
    deal = list(history[:32])
    ia = [i for i, r in enumerate(DEAL_ORDER) if r == a]
    ib = [i for i, r in enumerate(DEAL_ORDER) if r == b]
    for i, j in zip(ia, ib):
        deal[i], deal[j] = deal[j], deal[i]
    return deal + list(history[32:])


def test_skat_viewer_scene_and_observation_ignore_the_other_hands():
    g, sess = dealt_skat(4)
    s = sess.state
    assert g.current_player(s) == 0
    other = g.initial_state()
    for a in swap_hands([int(x) for x in s.history()], g, 1, 2):
        other = g.apply_action(other, a)
    assert json.dumps(g.scene(s, 0)) == json.dumps(g.scene(other, 0))
    assert g.observation(s, 1) != g.observation(other, 1)
    # a spectator sees everything
    hands = g.scene(s, None)["parts"][0]["hands"]
    assert [len(h) for h in hands] == [10, 10, 10]


def test_skat_scene_hand_is_exactly_the_viewers_hand():
    g, sess = dealt_skat(6)
    for viewer in (0, 1, 2):
        table = g.scene(sess.state, viewer)["parts"][0]
        hand = {(c["rank"], c["suit"]) for c in table["hand"]}
        mine = g.view_of(sess.state, viewer).hand
        assert len(hand) == len(mine) == 10
        assert table["handSizes"] == [10, 10, 10]


def test_skat_phases_buttons_and_privacy():
    g, sess = dealt_skat(8)
    s = sess.state
    labels = [g.action_label(s, a) for a in g.legal_actions(s)]
    assert labels[0] == "Pass" and "Grand" in labels and "Null" in labels
    buttons = [p for p in g.scene(s, 0)["parts"] if p["view"] == "buttons"]
    assert buttons and len(buttons[0]["choices"]) == 7
    # deal steps: card to seat 0 hidden from seats 1 and 2, the skat hidden from everyone
    to_me, to_west = sess.steps[0], sess.steps[3]
    skat = sess.steps[9]
    assert to_me.to_json(0, 1)["hidden"] and "a" in to_me.to_json(0, 0)
    assert to_west.to_json(3, 0)["hidden"] and "a" in to_west.to_json(3, 1)
    assert all(skat.to_json(9, v).get("hidden") for v in (0, 1, 2))
    assert "a" in skat.to_json(9, None)
    assert skat.to_json(9, 0)["text"] == "puts a card into the skat"


def test_skat_discard_is_private_and_hand_sizes_are_public():
    g = Skat()
    sess = Session(g, [Seat("bot", "sepp")] * 3, 5)
    while not sess.terminal and sess.to_move() != CHANCE:
        sess.step()
    while not sess.terminal and g.view_of(sess.state, max(sess.state.current_player(), 0)).phase != "discarding":
        sess.step()
    if not sess.terminal:
        declarer = g.current_player(sess.state)
        sess.step()
        step = sess.steps[-1]
        assert step.private == (declarer,)
        assert step.to_json(len(sess.steps) - 1, (declarer + 1) % 3)["text"] == "discards a card to the skat"
        s = sess.state
        for viewer in range(3):
            assert g.scene(s, viewer)["parts"][0]["handSizes"][declarer] in (11, 10)


def test_skat_bots_win_against_random():
    g = Skat()
    res = simulate(g, [g.make_policy("heidi"), g.make_policy("randy")], n=90, seed=1)
    assert res.mean_return(0) > res.mean_return(1)


# --------------------------------------------------------------------------- #
# Doppelkopf
# --------------------------------------------------------------------------- #
def dealt_dk(seed, **params):
    g = Doppelkopf(**params)
    sess = Session(g, [Seat("human")] + [Seat("bot", "hanni")] * 3, seed)
    sess.advance()
    return g, sess


def test_doppelkopf_params_reach_the_engine_and_rules():
    g = Doppelkopf(second_dulle=False, karlchen=False)
    assert g.engine.get_parameters() == {"second_dulle": False, "karlchen": False}
    assert g.initial_state().rules.second_dulle is False
    sess = play(g, seed=2)
    assert sess.terminal


def test_doppelkopf_other_hands_never_reach_the_viewer():
    g, sess = dealt_dk(3)
    s = sess.state
    base = json.dumps(g.scene(s, 0))
    obs = g.observation(s, 0)
    swapped = g.copy_state(s)
    swapped.hands[1], swapped.hands[2] = swapped.hands[2], swapped.hands[1]
    assert json.dumps(g.scene(swapped, 0)) == base
    assert g.observation(swapped, 0) == obs
    assert g.observation(swapped, 1) != g.observation(s, 1)
    table = g.scene(s, 0)["parts"][0]
    assert len(table["hand"]) == 12 and table["handSizes"] == [12, 12, 12, 12]
    assert "hands" not in table
    assert len(g.scene(s, None)["parts"][0]["hands"]) == 4


def test_doppelkopf_teams_stay_hidden_until_the_queens_are_played():
    g, sess = dealt_dk(5)
    s = sess.state
    table = g.scene(s, 0)["parts"][0]
    mine = "Re" if 0 in s.re_players else "Kontra"
    assert table["badges"][0] == [mine]
    assert all(b == [] for b in table["badges"][1:])
    while not sess.terminal:
        sess.act(g.legal_actions(sess.state)[0])
        sess.advance()
    final = g.scene(sess.state, 0)["parts"]
    assert final[-1]["view"] == "kv" and final[-1]["caption"] == "Result"
    badges = g.scene(sess.state, 0)["parts"][0]["badges"]
    assert sum(b == ["Re"] for b in badges) == len(sess.state.re_players)
    assert sum(b == ["Kontra"] for b in badges) == 4 - len(sess.state.re_players)


def test_doppelkopf_legal_cards_follow_the_rules_and_are_clickable():
    g, sess = dealt_dk(7)
    while not sess.terminal and not sess.state.current_trick:
        sess.act(g.legal_actions(sess.state)[0])
        sess.advance()
    assert sess.waiting_for_human() or sess.terminal
    if not sess.terminal:
        s = sess.state
        legal = set(g.legal_actions(s))
        clickable = {c["action"] for c in g.scene(s, 0)["parts"][0]["hand"] if "action" in c}
        assert clickable == legal


def test_doppelkopf_deals_are_private_and_plays_public():
    g, sess = dealt_dk(2)
    deal = sess.steps[0]
    assert deal.private == (0,) and deal.to_json(0, 1)["hidden"]
    assert deal.to_json(0, 1)["text"] == "deals a card to South"
    assert deal.to_json(0, 0)["text"].startswith("deals ")
    sess.act(g.legal_actions(sess.state)[0])
    play_step = sess.steps[-1]
    assert play_step.player == 0 and play_step.private is None
    assert "hidden" not in play_step.to_json(len(sess.steps) - 1, 3)


def test_doppelkopf_bot_ladder_and_master_speed():
    import time
    g = Doppelkopf()
    res = simulate(g, [g.make_policy("hanni"), g.make_policy("randy")], n=40, seed=1)
    assert res.mean_return(0) > 0
    t = time.time()
    sess = play(g, "master", seed=1)
    assert sess.terminal and time.time() - t < 5
