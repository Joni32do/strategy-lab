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

    # ---- non-playable envs are refused ----
    code, d = post(c, "/api/env/new", {"envId": "Ant-v5"})
    assert code == 400 and "not playable" in d["error"], d
    code, d = post(c, "/api/env/new", {"envId": "NoSuchEnv-v0"})
    assert code == 400, d
    print("ok  env/new refuses mujoco + unknown ids")

    # ---- registry advertises what is playable ----
    d = c.get("/api/gym/envs").get_json()
    assert d["playable_namespaces"] == ["classic_control", "toy_text"], d
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

    print("\nALL PASSED")


if __name__ == "__main__":
    main()
