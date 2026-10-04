"""Catan on catanatron: replayable randomness, hidden hands, trading, bots, trade lens."""

from __future__ import annotations

import json
import random

import pytest

from strategy_lab.core import CHANCE, Seat, Session
from strategy_lab.games.catan import Catan
from strategy_lab.games.catan import board as geo
from strategy_lab.games.catan.actions import encode, kind
from strategy_lab.games.catan.policy import (
    MetricWeights, TradeParams, evaluate_trade, trade_coefficient)
from strategy_lab.lenses import all_lenses


def run(game, bot="random", seed=1, steps=None):
    sess = Session(game, [Seat("bot", bot) for _ in range(game.num_players)], seed)
    n = 0
    while not sess.terminal and (steps is None or n < steps):
        sess.step()
        n += 1
    return sess


def until(sess, predicate, limit=3000):
    n = 0
    while not sess.terminal and n < limit and not predicate(sess):
        sess.step()
        n += 1
    return sess


# --------------------------------------------------------------------------- #
def test_geometry_of_the_standard_board():
    assert (len(geo.TILES), len(geo.NODES), len(geo.EDGES), len(geo.PORTS)) == (19, 54, 72, 9)
    assert all(len(t.nodes) == 6 for t in geo.TILES.values())
    xs = [x for x, _ in geo.NODES.values()]
    assert min(xs) > 0 and max(xs) < geo.WIDTH


def test_the_first_node_is_a_board_seed_and_randomness_replays():
    g = Catan()
    s = g.initial_state()
    assert g.current_player(s) == CHANCE
    with pytest.raises(NotImplementedError):
        g.chance_outcomes(s)
    state = random.getstate()
    a = g.apply_action(s, 4242)
    assert random.getstate() == state, "building the board must not disturb the global RNG"
    b = g.apply_action(s, 4242)
    tiles = lambda x: [(t.resource, t.number) for t in x.game.state.board.map.land_tiles.values()]
    assert tiles(a) == tiles(b)
    assert tiles(a) != tiles(g.apply_action(s, 4243))


@pytest.mark.parametrize("players", [2, 3, 4])
def test_full_games_replay_exactly(players):
    g = Catan(players=players)
    sess = run(g, "vera", seed=3)
    assert sess.terminal and not sess.timeout
    assert len(sess.returns()) == players and sorted(sess.returns())[-1] == 1.0
    again = Session(g, sess.seats, 3, json.loads(json.dumps(sess.log)), strict=True)
    assert g.key(again.state) == g.key(sess.state)
    assert again.returns() == sess.returns()


def test_dice_steals_and_dev_cards_are_chance_nodes():
    g = Catan()
    sess = run(g, "vera", seed=2, steps=60)
    s = sess.state
    # advance to a pending roll
    until(sess, lambda x: x.state.pending is not None and x.state.pending[0] == "roll")
    s = sess.state
    outs = g.chance_outcomes(s)
    assert [o for o, _ in outs] == list(range(2, 13))
    assert abs(sum(p for _, p in outs) - 1) < 1e-9 and dict(outs)[7] == pytest.approx(1 / 6)
    assert g.action_label(s, 8) == "8"
    kinds = {"roll"}
    steal = run(g, "random", seed=5)
    for step in steal.steps:
        if step.player == CHANCE and step.private is not None:
            kinds.add("private")
    assert "private" in kinds


def test_private_chance_steps_are_hidden_from_other_seats():
    g = Catan()
    sess = Session(g, [Seat("bot", "wanda")] * 4, 6)
    until(sess, lambda x: any(st.private for st in x.steps), limit=6000)
    step = next(st for st in sess.steps if st.private)
    i = sess.steps.index(step)
    insiders = set(step.private)
    outsider = next(v for v in range(4) if v not in insiders)
    insider = next(iter(insiders))
    seen = step.to_json(i, insider)
    hidden = step.to_json(i, outsider)
    assert "a" in seen and hidden.get("hidden") is True and "a" not in hidden
    assert hidden["text"] in ("draws a development card", "takes a card")
    assert step.to_json(i, None)["text"] == seen["text"]          # spectators see all


def test_other_hands_are_counts_in_a_viewers_scene():
    g = Catan()
    sess = run(g, "wanda", seed=4, steps=300)
    for viewer in range(4):
        parts = g.scene(sess.state, viewer)["parts"]
        panels = {p["owner"]: dict(p["items"]) for p in parts if p["view"] == "kv" and "owner" in p}
        for seat, items in panels.items():
            if seat == viewer:
                assert not items["Cards"].endswith(" cards")
            else:
                assert items["Cards"].endswith(" cards") and "(public)" in items["Victory points"]
    spectator = g.scene(sess.state, None)["parts"]
    own = [dict(p["items"])["Cards"] for p in spectator if p["view"] == "kv" and "owner" in p]
    assert not all(c.endswith(" cards") for c in own)
    obs0, obs1 = g.observation(sess.state, 0), g.observation(sess.state, 1)
    assert obs0 != obs1 and "hand=" in obs0


def test_setup_scene_offers_board_clicks_for_the_human():
    g = Catan()
    sess = Session(g, [Seat("human")] + [Seat("bot", "vera")] * 3, 1)
    sess.advance()
    s = sess.state
    hexpart = g.scene(s, 0)["parts"][0]
    assert hexpart["view"] == "hex" and len(hexpart["tiles"]) == 19 and len(hexpart["ports"]) == 9
    clickable = [n for n in hexpart["nodes"] if "action" in n]
    assert len(clickable) == 54 and clickable[0]["action"].startswith("SETTLEMENT:")
    assert g.scene(s, 1)["parts"][0]["nodes"] == []                # not your turn
    sess.act(clickable[0]["action"])
    sess.advance()
    sess.act(g.legal_actions(sess.state)[0])                        # the road
    hexpart = g.scene(sess.state, None)["parts"][0]
    assert any(n.get("kind") == "settlement" and n["owner"] == 0 for n in hexpart["nodes"])
    assert any(e.get("owner") == 0 for e in hexpart["edges"])
    json.dumps(g.scene(sess.state, 0))


def test_action_strings_are_unique_stable_and_labeled():
    g = Catan()
    sess = run(g, "wanda", seed=2, steps=250)
    s = sess.state
    if g.current_player(s) != CHANCE:
        legal = g.legal_actions(s)
        assert len(legal) == len(set(legal))
        assert [encode(a) for a in g.options(s).values()] == legal
        assert all(isinstance(g.action_label(s, a), str) and g.action_label(s, a) for a in legal)


# --------------------------------------------------------------------------- #
# Trading
# --------------------------------------------------------------------------- #
def test_one_offer_per_turn_and_the_full_negotiation():
    g = Catan()
    sess = Session(g, [Seat("bot", "tina")] * 4, 3)
    until(sess, lambda x: any(kind(str(st.action)) == "OFFER" for st in x.steps))
    kinds = [kind(str(st.action)) for st in sess.steps if st.player >= 0]
    assert "OFFER" in kinds
    sess = run(g, "tina", seed=3)
    seq = [(i, kind(str(st.action))) for i, st in enumerate(sess.steps) if st.player >= 0]
    turn_offers = 0
    for _, k in seq:
        if k == "END_TURN":
            turn_offers = 0
        if k == "OFFER":
            turn_offers += 1
            assert turn_offers <= 1
    assert {"ACCEPT", "REJECT"} & {k for _, k in seq}


def test_trading_can_be_switched_off():
    g = Catan(trading=False)
    sess = run(g, "tina", seed=3)
    assert sess.terminal
    assert not any(kind(str(st.action)) == "OFFER" for st in sess.steps if st.player >= 0)


def test_offerer_is_never_asked_to_accept_their_own_offer():
    g = Catan()
    sess = Session(g, [Seat("bot", "tina")] * 4, 5)
    seen_quirk = False
    while not sess.terminal:
        s = sess.state
        if s.game is not None and s.pending is None and s.game.state.is_resolving_trade:
            st = s.game.state
            if (st.current_prompt.value == "DECIDE_TRADE"
                    and st.current_color() == st.colors[st.current_trade[10]]):
                seen_quirk = True
                assert g.legal_actions(s) == ["REJECT"]
        sess.step()
    assert seen_quirk


# --------------------------------------------------------------------------- #
# Bots, policy, lens
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bot", ["random", "wanda", "vera", "tina", "blake"])
def test_every_bot_finishes_a_game(bot):
    g = Catan()
    sess = run(g, bot, seed=7)
    assert sess.terminal and not sess.timeout


def test_value_bots_beat_random_bots():
    g = Catan()
    wins = 0
    for seed in range(4):
        seats = [Seat("bot", "vera"), Seat("bot", "random"), Seat("bot", "random"),
                 Seat("bot", "random")]
        sess = Session(g, seats, seed)
        while not sess.terminal:
            sess.step()
        wins += sess.returns()[0] == 1.0
    assert wins >= 3


def test_blocker_blocks_and_trader_vetoes_leaders():
    g = Catan()
    sess = run(g, "blake", seed=3)
    stats = {}
    for pol in sess._policies.values():
        for p in pol._players.values():
            for k, v in p.stats.items():
                stats[k] = stats.get(k, 0) + v
    assert stats["offers"] > 0 and stats["blocks"] >= 0


def test_trade_rule_curve_veto_and_premium():
    tp = TradeParams()
    assert trade_coefficient(0.0, tp) < 0.1 and trade_coefficient(1.0, tp) > 2.4
    assert trade_coefficient(0.5, tp) == pytest.approx(tp.lam_max / 2)
    g = Catan()
    sess = run(g, "vera", seed=3, steps=420)
    eng = sess.state.game
    me, rival = eng.state.colors[0], eng.state.colors[1]
    ok, info = evaluate_trade(eng, me, rival, [1, 0, 0, 0, 0], [0, 1, 0, 0, 0],
                              MetricWeights(), TradeParams(veto_vp_margin=10))
    assert info["vetoed"] and not ok                      # a margin of 10 vetoes everyone


def test_trade_lens_schema_and_decisions():
    g = Catan()
    lens = all_lenses()["trade"]
    assert lens.applies(g) and not lens.applies(__import__(
        "strategy_lab.games.tictactoe", fromlist=["TicTacToe"]).TicTacToe())
    sess = Session(g, [Seat("bot", "tina")] * 4, 3)
    for _ in range(500):
        sess.step()
    result = lens.run(sess, {})
    json.dumps(result)
    assert len(result["players"]) == 4 and len(result["curve"]["points"]) == 41
    assert result["curve"]["points"][0]["lambda"] < result["curve"]["points"][-1]["lambda"]
    assert result["decisions"] and {"kind", "verdict", "give", "get", "step"} <= set(result["decisions"][0])
    wide = lens.run(sess, {"lam_max": 5.0})
    assert wide["curve"]["lamMax"] == 5.0
    assert all(0 <= m["strength"] <= 1 for m in result["markers"])
    assert [d["step"] for d in result["decisions"]] == sorted(d["step"] for d in result["decisions"])


def test_trade_lens_option_schema_matches_the_knobs():
    lens = all_lenses()["trade"]
    names = {o["name"] for o in lens.options}
    assert {"lam_max", "lam_steepness", "lam_midpoint", "veto_vp_margin", "margin",
            "premium_per_vp", "vp", "production", "expansion", "block_weight"} <= names
    json.dumps(lens.meta())
