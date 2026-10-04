"""Conformance: every registered game must honor the Game contract.

New games are covered automatically: drop a module into
``strategy_lab/games`` and these tests play it with random moves, with
each bot and with each rule card, replay its logs, and check that its
scenes serialize to JSON. Slow engines may set ``conformance_steps`` on
the game class to cap these playouts.
"""

from __future__ import annotations

import json
import math

import pytest

from strategy_lab.core import CHANCE, Seat, Session
from strategy_lab.core import registry
from strategy_lab.learn.concepts import concept_ids
from strategy_lab.learn.curriculum import CHAPTERS

GAMES = registry.games()
IDS = [g.id for g in GAMES]
CHALLENGE_KINDS = {"finish", "win", "draw", "score", "lens", "sim"}


def test_no_broken_modules():
    assert registry.broken() == {}, "\n".join(registry.broken().values())


@pytest.mark.parametrize("cls", GAMES, ids=IDS)
def test_metadata(cls):
    g = cls()
    assert g.name and g.tagline, "name and tagline are required"
    assert g.chapter in {c.id for c in CHAPTERS}, f"unknown chapter {g.chapter!r}"
    unknown = set(g.concepts) - concept_ids()
    assert not unknown, f"unknown concept ids {unknown}"
    card_ids = {c.id for c in g.cards()}
    assert len(card_ids) == len(g.cards()), "duplicate card ids"
    bot_ids = {b.id for b in g.bots}
    for b in g.bots:
        assert set(b.cards) <= card_ids, f"bot {b.id} uses unknown cards"
        if b.policy:
            assert callable(getattr(g, b.policy, None)), f"bot {b.id}: no method {b.policy}"
    for ch in g.challenges:
        assert ch.kind in CHALLENGE_KINDS, f"challenge {ch.id}: bad kind {ch.kind}"
        if ch.bot:
            assert ch.bot in bot_ids, f"challenge {ch.id}: unknown bot {ch.bot}"
    json.dumps(g.detail())


def _check_state(g, s, viewer):
    json.dumps(g.scene(s, viewer))
    assert isinstance(g.status(s, viewer), str)
    if g.is_terminal(s):
        r = g.returns(s)
        assert len(r) == g.num_players
        return
    p = g.current_player(s)
    if p == CHANCE:
        try:
            outs = g.chance_outcomes(s)
        except NotImplementedError:
            return
        assert outs, "chance node without outcomes"
        assert math.isclose(sum(pr for _, pr in outs), 1.0, abs_tol=1e-6)
        for a, _ in outs:
            assert isinstance(a, (int, str)) and not isinstance(a, bool)
    else:
        assert 0 <= p < g.num_players
        legal = g.legal_actions(s)
        assert legal, "non-terminal decision node without legal actions"
        for a in legal:
            assert isinstance(a, (int, str)) and not isinstance(a, bool)
            assert isinstance(g.action_label(s, a), str)


def _play(g, seats, seed, check_every=1):
    sess = Session(g, seats, seed)
    cap = g.conformance_steps
    n = 0
    while not sess.terminal:
        if n % check_every == 0:
            _check_state(g, sess.state, 0)
        if cap is not None and n >= cap:
            sess.capped = True
            return sess
        if not sess.step():
            break
        n += 1
    _check_state(g, sess.state, 0)
    sess.capped = False
    return sess


@pytest.mark.parametrize("cls", GAMES, ids=IDS)
def test_random_playouts_and_replay(cls):
    g = cls()
    for seed in range(3):
        sess = _play(g, [Seat("bot", "random") for _ in range(g.num_players)], seed,
                     check_every=1 if seed == 0 else 25)
        assert sess.terminal or sess.capped, "game did not end"
        again = Session(g, sess.seats, seed, sess.log, strict=True)
        assert again.replay_error is None
        assert g.key(again.state) == g.key(sess.state), "replay is not deterministic"
        assert again.returns() == sess.returns()


@pytest.mark.parametrize("cls", GAMES, ids=IDS)
def test_every_bot_plays(cls):
    g = cls()
    for b in g.bots:
        sess = _play(g, [Seat("bot", b.id) for _ in range(g.num_players)], 7, check_every=50)
        assert sess.terminal or sess.capped, f"bot {b.id}: game did not end"


@pytest.mark.parametrize("cls", GAMES, ids=IDS)
def test_every_card_plays(cls):
    g = cls()
    for card in g.cards():
        seats = [Seat("bot", "random", cards=[card.id])]
        seats += [Seat("bot", "random") for _ in range(g.num_players - 1)]
        sess = _play(g, seats, 11, check_every=50)
        assert sess.terminal or sess.capped, f"card {card.id}: game did not end"


@pytest.mark.parametrize("cls", GAMES, ids=IDS)
def test_human_seat_flow(cls):
    """A human seat waits; acting with a legal action continues the game."""
    g = cls()
    seats = [Seat("human")] + [Seat("bot", "random") for _ in range(g.num_players - 1)]
    sess = Session(g, seats, 3)
    sess.advance()
    turns = 0
    while not sess.terminal and turns < 30:
        assert sess.waiting_for_human()
        sess.act(g.legal_actions(sess.state)[0])
        sess.advance()
        turns += 1
    replay = Session(g, seats, 3, sess.log, strict=True)
    assert g.key(replay.state) == g.key(sess.state)
