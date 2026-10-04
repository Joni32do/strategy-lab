"""Play-session API tests (gymnasium + open_spiel), in-process.

Run: uv run python server/test_envs.py
"""
import json

from app import app


def post(c, url, body=None):
    r = c.post(url, data=json.dumps(body or {}), content_type="application/json")
    return r.status_code, r.get_json()


def main():
    c = app.test_client()

    # ---- gym env lifecycle: FrozenLake (ansi render, discrete actions) ----
    code, d = post(c, "/api/env/new", {"envId": "FrozenLake-v1", "seed": 7})
    assert code == 200, d
    assert d["envId"] == "FrozenLake-v1" and d["steps"] == 0 and d["done"] is False
    assert d["actionSpace"]["type"] == "discrete" and d["actionSpace"]["n"] == 4
    assert d["actionSpace"]["names"] == ["left", "down", "right", "up"]
    assert isinstance(d["render"], str) and "S" in d["render"]
    sid = d["sid"]
    print("ok  env/new FrozenLake: obs=%r render present" % d["obs"])

    code, d = post(c, "/api/env/%s/step" % sid, {"action": 2})
    assert code == 200 and d["steps"] == 1 and "reward" in d, d
    code, d = post(c, "/api/env/%s/step" % sid, {"policy": "random"})
    assert code == 200 and d["steps"] == 2, d
    print("ok  env/step: concrete action + random policy both work")

    code, d = post(c, "/api/env/%s/step" % sid, {"action": 99})
    assert code == 400, d
    code, d = post(c, "/api/env/nope/step", {"action": 0})
    assert code == 404, d
    print("ok  env/step: bad action 400, bad session 404")

    code, d = post(c, "/api/env/%s/reset" % sid, {"seed": 7})
    assert code == 200 and d["steps"] == 0 and d["total"] == 0, d
    print("ok  env/reset")

    # ---- CartPole: vector obs, no ansi render ----
    code, d = post(c, "/api/env/new", {"envId": "CartPole-v1", "seed": 1})
    assert code == 200 and len(d["obs"]) == 4 and d["render"] is None, d
    code, d = post(c, "/api/env/%s/step" % d["sid"], {"action": 1})
    assert code == 200 and isinstance(d["obs"], list), d
    print("ok  CartPole: 4-dim obs vector, steps fine without render")

    # ---- Qwixx: the lab's own gym env (server/qwixx_env.py) ----
    code, d = post(c, "/api/env/new", {"envId": "strategy_lab/Qwixx-v0", "seed": 5})
    assert code == 200, d
    assert d["actionSpace"]["type"] == "discrete" and d["actionSpace"]["n"] == 45, d["actionSpace"]
    names = d["actionSpace"]["names"]
    assert names[0] == "red 2" and names[33] == "blue 12" and names[44] == "pass", names[:3]
    assert "QWIXX" in d["render"] and "your sheet" in d["render"], d["render"][:80]
    sid = d["sid"]
    print("ok  env/new Qwixx: 45 self-named actions, ansi sheet rendered")

    # a masked env publishes its legal actions so the UI can grey out the rest
    legal = d["legalActions"]
    assert 44 in legal and 0 < len(legal) < 45, legal        # pass is always there
    assert all(names[i].split()[0] in ("red", "yellow", "green", "blue", "pass")
               for i in legal), [names[i] for i in legal]
    print("ok  env/new Qwixx: legalActions published (%d of 45 open)" % len(legal))

    # an illegal but in-range action is a no-op, not a silent penalty
    bad = next(i for i in range(45) if i not in legal)
    code, e = post(c, "/api/env/%s/step" % sid, {"action": bad})
    # the step is counted (it burns time-limit budget) but the sheet is not touched
    assert code == 200 and e["steps"] == 1 and e["reward"] == 0, e
    assert e["render"] == d["render"] and e["legalActions"] == legal, "state must be unchanged"
    print("ok  env/step Qwixx: illegal cross '%s' left the game untouched" % names[bad])

    # "policy: random" goes through the env's action mask, so it plays
    # legal Qwixx rather than bouncing off rejected clicks
    guard = 0
    while not d["done"] and guard < 300:
        code, d = post(c, "/api/env/%s/step" % sid, {"policy": "random"})
        assert code == 200, d
        guard += 1
    assert d["done"] and d["terminated"] and not d["truncated"], d
    assert "GAME OVER" in d["render"], d["render"][-200:]
    print("ok  env/step Qwixx: random policy played a full game in %d steps (return %s)"
          % (d["steps"], d["total"]))

    code, d = post(c, "/api/env/%s/reset" % sid, {"seed": 5})
    assert code == 200 and d["steps"] == 0 and d["done"] is False, d
    code, d = post(c, "/api/env/%s/step" % sid, {"action": 45})
    assert code == 400, d
    print("ok  env/reset Qwixx + out-of-range action refused")

    # ---- non-playable envs are refused ----
    code, d = post(c, "/api/env/new", {"envId": "Ant-v5"})
    assert code == 400 and "not playable" in d["error"], d
    code, d = post(c, "/api/env/new", {"envId": "NoSuchEnv-v0"})
    assert code == 400, d
    print("ok  env/new refuses mujoco + unknown ids")

    # ---- registry advertises what is playable ----
    d = c.get("/api/gym/envs").get_json()
    assert d["playable_namespaces"] == ["classic_control", "toy_text", "strategy_lab"], d
    local = next((g for g in d["groups"] if g["namespace"] == "strategy_lab"), None)
    assert local and "strategy_lab/Qwixx-v0" in local["envs"], d["groups"]
    assert d["open_spiel"]["available"] is True, d["open_spiel"]
    assert "skat" in d["open_spiel"]["games"] and "chess" in d["open_spiel"]["games"]
    print("ok  /api/gym/envs: playable namespaces + pyspiel available (%d games)"
          % len(d["open_spiel"]["games"]))

    # ---- open_spiel: tic_tac_toe full game on random policy ----
    code, d = post(c, "/api/spiel/new", {"game": "tic_tac_toe", "seed": 3})
    assert code == 200 and d["players"] == 2 and d["terminal"] is False, d
    assert d["cur"] == d["humanSeat"] and len(d["legal"]) == 9
    assert all(isinstance(a["a"], int) and isinstance(a["s"], str) for a in d["legal"])
    sid = d["sid"]
    guard = 0
    while not d["terminal"] and guard < 20:
        code, d = post(c, "/api/spiel/%s/act" % sid, {"policy": "random"})
        assert code == 200, d
        guard += 1
    assert d["terminal"] and isinstance(d["returns"], list) and len(d["returns"]) == 2
    print("ok  spiel tic_tac_toe: played to the end, returns=%s" % d["returns"])

    # ---- open_spiel: skat deals (chance) and reaches the human's bid ----
    code, d = post(c, "/api/spiel/new", {"game": "skat", "seed": 11})
    assert code == 200 and d["players"] == 3 and d["terminal"] is False, d
    assert d["cur"] == d["humanSeat"] and len(d["legal"]) >= 2, d
    assert "Hand:" in d["obs"], d["obs"][:80]
    sid = d["sid"]
    code, d = post(c, "/api/spiel/%s/act" % sid, {"action": d["legal"][0]["a"]})
    assert code == 200, d
    # after our action the bots act until it is our turn again (or terminal)
    assert d["terminal"] or d["cur"] == d["humanSeat"], d
    assert len(d["log"]) >= 1
    print("ok  spiel skat: dealt, human bid applied, bots advanced (log %d entries)"
          % len(d["log"]))

    # play a full skat deal on random to prove termination
    guard = 0
    while not d["terminal"] and guard < 200:
        code, d = post(c, "/api/spiel/%s/act" % sid, {"policy": "random"})
        assert code == 200, d
        guard += 1
    assert d["terminal"] and len(d["returns"]) == 3, d
    print("ok  spiel skat: full deal terminates, returns=%s" % d["returns"])

    # ---- open_spiel: chess FEN observation + illegal action rejected ----
    code, d = post(c, "/api/spiel/new", {"game": "chess", "seed": 5})
    assert code == 200 and "/" in d["obs"] and len(d["legal"]) == 20, d
    sid = d["sid"]
    illegal = max(a["a"] for a in d["legal"]) + 1
    code, e = post(c, "/api/spiel/%s/act" % sid, {"action": illegal})
    assert code == 400, e
    code, d = post(c, "/api/spiel/%s/act" % sid, {"action": d["legal"][0]["a"]})
    assert code == 200 and (d["terminal"] or d["cur"] == d["humanSeat"]), d
    print("ok  spiel chess: FEN obs, 20 openings, illegal rejected, bot replied")

    # ---- open_spiel: doppelkopf is registered (vendored python game) ----
    d = c.get("/api/gym/envs").get_json()
    assert "python_doppelkopf" in d["open_spiel"]["games"], d["open_spiel"]
    code, d = post(c, "/api/spiel/new", {"game": "python_doppelkopf", "seed": 7})
    assert code == 200 and d["players"] == 4 and d["terminal"] is False, d
    assert d["cur"] == d["humanSeat"] and len(d["legal"]) >= 1, d
    assert d["obs"].startswith("p0 hand:"), d["obs"][:40]
    print("ok  spiel doppelkopf: registered, dealt, human to play (%d legal)"
          % len(d["legal"]))

    # rule toggles ride along as game parameters; a full deal still ends
    # zero-sum whether the special rules are on or off
    code, d = post(c, "/api/spiel/new", {
        "game": "python_doppelkopf", "seed": 7,
        "params": {"second_dulle": False, "karlchen": False}})
    assert code == 200, d
    sid = d["sid"]
    guard = 0
    while not d["terminal"] and guard < 300:
        code, d = post(c, "/api/spiel/%s/act" % sid, {"policy": "random"})
        assert code == 200, d
        guard += 1
    assert d["terminal"] and len(d["returns"]) == 4, d
    assert abs(sum(d["returns"])) < 1e-6, d["returns"]
    print("ok  spiel doppelkopf: rule params applied, deal terminates zero-sum")

    code, d = post(c, "/api/spiel/new", {"game": "no_such_game"})
    assert code == 400, d
    print("ok  spiel/new refuses unknown game")

    # ---- cardView: doppelkopf table view ----
    import time
    from envs import SPIEL_SESSIONS

    code, d = post(c, "/api/spiel/new", {"game": "python_doppelkopf", "seed": 7})
    assert code == 200, d
    cv = d["cardView"]
    assert cv["kind"] == "doppelkopf" and cv["players"] == 4, cv
    assert cv["phase"] == "play" and cv["status"], cv
    assert cv["handSizes"] == [12, 12, 12, 12], cv["handSizes"]
    assert len(cv["hand"]) == 12, len(cv["hand"])
    for h in cv["hand"]:
        assert h["rank"] and 0 <= h["suit"] <= 3 and isinstance(h["points"], int), h
    legal_cards = [h for h in cv["hand"] if isinstance(h["a"], int)]
    assert legal_cards, "expected at least one legal card with an int 'a'"
    assert len(cv["seatNames"]) == 4 and cv["seatNames"][cv["humanSeat"]] == "You"
    sid = d["sid"]
    print("ok  cardView doppelkopf: kind/players/phase, 12-card hand, %d legal"
          % len(legal_cards))

    # bots attached (3 non-human seats) - checkpoints are committed
    bots = SPIEL_SESSIONS[sid].get("bots")
    if bots:
        assert len(bots) == 3, bots
        print("ok  doppelkopf bots: 3 PIMC master bots attached")
    else:
        print("SKIP doppelkopf bots: checkpoint failed to load (random seats)")

    # play a legal card via the API; time this /act (human + bots advance)
    t0 = time.time()
    code, d = post(c, "/api/spiel/%s/act" % sid, {"action": legal_cards[0]["a"]})
    dt = time.time() - t0
    assert code == 200, d
    print("ok  doppelkopf /act latency: %.3fs (human card + non-human seats)" % dt)
    cv = d["cardView"]
    assert cv["handSizes"][cv["humanSeat"]] < 12, cv["handSizes"]
    for pl in cv["trick"]["plays"]:
        assert 0 <= pl["seat"] < 4 and 0 <= pl["suit"] <= 3, pl
    if cv["lastTrick"]:
        assert 0 <= cv["lastTrick"]["winner"] < 4
        for pl in cv["lastTrick"]["plays"]:
            assert 0 <= pl["seat"] < 4 and 0 <= pl["suit"] <= 3, pl
    print("ok  cardView doppelkopf: hand shrank, trick/lastTrick consistent")

    # play to terminal on random -> result present and coherent
    guard = 0
    while not cv["terminal"] and guard < 300:
        code, d = post(c, "/api/spiel/%s/act" % sid, {"policy": "random"})
        assert code == 200, d
        cv = d["cardView"]
        guard += 1
    res = cv["result"]
    assert res is not None and len(res["returns"]) == 4, res
    assert abs(sum(res["returns"])) < 1e-6, res["returns"]
    assert res["re_points"] + res["kontra_points"] == 240, res
    print("ok  cardView doppelkopf: terminal result, returns sum 0, points=240")

    # ---- cardView: skat table view ----
    code, d = post(c, "/api/spiel/new", {"game": "skat", "seed": 11})
    assert code == 200, d
    cv = d["cardView"]
    assert cv["kind"] == "skat" and cv["players"] == 3, cv
    assert cv["phase"] == "bid", cv["phase"]
    assert cv["actions"], "expected non-card bid actions in bid phase"
    assert len(cv["hand"]) == 10, len(cv["hand"])
    for h in cv["hand"]:
        assert 0 <= h["suit"] <= 3 and h["rank"], h
    sid = d["sid"]
    print("ok  cardView skat: kind/players, bid phase, %d actions, 10-card hand"
          % len(cv["actions"]))

    # drive through bidding/discard by choosing legal actions until play phase
    guard = 0
    while not cv["terminal"] and cv["phase"] != "play" and guard < 60:
        if cv["actions"]:
            action = cv["actions"][0]["a"]
        else:
            action = next(h["a"] for h in cv["hand"] if h["a"] is not None)
        code, d = post(c, "/api/spiel/%s/act" % sid, {"action": action})
        assert code == 200, d
        cv = d["cardView"]
        guard += 1
    assert cv["terminal"] or cv["phase"] == "play", cv["phase"]
    if not cv["terminal"] and cv["toAct"] == cv["humanSeat"]:
        assert any(isinstance(h["a"], int) for h in cv["hand"]), cv["hand"]
        print("ok  cardView skat: reached play phase, legal cards carry 'a'")
    else:
        print("ok  cardView skat: reached play phase (bots to act)")

    # play to terminal -> result.returns has 3 entries
    guard = 0
    while not cv["terminal"] and guard < 200:
        code, d = post(c, "/api/spiel/%s/act" % sid, {"policy": "random"})
        assert code == 200, d
        cv = d["cardView"]
        guard += 1
    assert cv["terminal"] and len(cv["result"]["returns"]) == 3, cv["result"]
    print("ok  cardView skat: terminal result.returns has 3 entries")

    # other games carry NO cardView key
    code, d = post(c, "/api/spiel/new", {"game": "tic_tac_toe", "seed": 3})
    assert code == 200 and "cardView" not in d, list(d)
    print("ok  cardView absent for non-card game (tic_tac_toe)")

    print("\nALL PASSED")


if __name__ == "__main__":
    main()
