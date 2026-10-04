"""The HTTP API, exercised in-process with Flask's test client."""

from __future__ import annotations

import pytest

from strategy_lab.web import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path, dev=True)
    return app.test_client()


def play(client, **body):
    body.setdefault("game", "tictactoe")
    r = client.post("/api/play", json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_catalog_lists_tictactoe_in_its_chapter(client):
    data = client.get("/api/catalog").get_json()
    trees = next(c for c in data["chapters"] if c["id"] == "trees")
    ids = [g["id"] for fam in trees["families"] for g in fam["games"]]
    assert "tictactoe" in ids
    fam = next(f for f in trees["families"] if any(g["id"] == "tictactoe" for g in f["games"]))
    assert fam["base"] == "MNKGame"


def test_game_detail_has_cards_bots_and_lenses(client):
    d = client.get("/api/games/tictactoe").get_json()
    assert {c["id"] for c in d["cards"]} >= {"win", "block", "fork"}
    assert {b["id"] for b in d["bots"]} >= {"randy", "minnie"}
    lens_ids = {l["id"] for l in d["lenses"]}
    assert {"cards", "model"} <= lens_ids
    assert d["lineage"] == ["Game", "MNKGame", "TicTacToe"]


def test_play_loop_records_history_once(client):
    seats = [{"kind": "human"}, {"kind": "bot", "bot": "randy"}]
    st = play(client, seats=seats, seed=5, sid="s1")
    assert st["humanTurn"] and st["legal"]
    while not st["terminal"]:
        st = play(client, seats=seats, seed=5, sid="s1", log=st["log"],
                  action=st["legal"][0]["a"])
    assert st["outcome"] in ("win", "draw", "loss")
    assert st["achieved"] is not None
    # replaying the finished game does not record it again
    again = play(client, seats=seats, seed=5, sid="s1", log=st["log"])
    assert again["achieved"] is None
    hist = client.get("/api/history").get_json()["games"]
    assert len(hist) == 1 and hist[0]["game"] == "tictactoe"


def test_illegal_action_is_reported_not_applied(client):
    seats = [{"kind": "human"}, {"kind": "bot", "bot": "randy"}]
    st = play(client, seats=seats, seed=1)
    bad = play(client, seats=seats, seed=1, log=st["log"], action=99)
    assert bad["error"] and bad["count"] == st["count"]


def test_replay_error_keeps_valid_prefix(client):
    seats = [{"kind": "human"}, {"kind": "bot", "bot": "randy"}]
    log = [{"p": 0, "a": 4}, {"p": 1, "a": 4}]
    st = play(client, seats=seats, seed=1, log=log)
    assert st["replayError"] and st["log"][0] == {"p": 0, "a": 4}


def test_undo_returns_to_human_turn(client):
    seats = [{"kind": "human"}, {"kind": "bot", "bot": "randy"}]
    st = play(client, seats=seats, seed=2)
    st = play(client, seats=seats, seed=2, log=st["log"], action=4)
    back = play(client, seats=seats, seed=2, log=st["log"], undo=True)
    assert back["count"] == 0 and back["humanTurn"]


def test_lenses_run_and_count_for_challenges(client):
    seats = [{"kind": "human"}, {"kind": "bot", "bot": "randy"}]
    r = client.post("/api/lens/cards", json={"game": "tictactoe", "seats": seats,
                                             "options": {"stack": ["win", "center"]},
                                             "sid": "x"})
    res = r.get_json()["result"]
    assert res["trace"]["card"] == "center"
    r = client.post("/api/lens/model", json={"game": "tictactoe", "seats": seats})
    assert r.get_json()["result"]["classes"] == 3


def test_simulate_and_sim_challenge(client):
    stack = ["win", "block", "fork", "smother", "center", "mirror-corner", "corner", "edge"]
    r = client.post("/api/simulate", json={"game": "tictactoe", "stack": stack,
                                           "bot": "minnie", "n": 100})
    data = r.get_json()
    assert data["stats"]["wins"][1] == 0
    assert "perfect-stack" in data["achieved"]["stars"]["tictactoe"]


def test_profile_patch_and_unlock_all(client):
    prof = client.get("/api/profile").get_json()
    assert prof["profile"]["tutorial"]["intro"] is False
    r = client.patch("/api/profile", json={"settings": {"unlockAll": True},
                                          "tutorial": {"intro": True}})
    d = r.get_json()
    assert d["profile"]["settings"]["unlockAll"] is True
    assert "tictactoe" in d["progress"]["unlocked"]


def test_concepts_endpoint(client):
    data = client.get("/api/concepts").get_json()
    ids = {c["id"] for c in data["concepts"]}
    assert {"probability", "nash-equilibrium", "q-learning"} <= ids
