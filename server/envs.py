"""Play sessions for the browse-able engines.

Two kinds of session, both in-memory and capped:

  Gymnasium (single-agent):   POST /api/env/new | /api/env/<sid>/step | reset
  OpenSpiel  (n-player):      POST /api/spiel/new | /api/spiel/<sid>/act

The point of the lab is exploration, so a "step" can be a concrete
action (the human plays) or {"policy": "random"} (watch a policy act
from the same state) - that is the policy-exploration hook.

Gymnasium envs are playable for the namespaces that work out of the
box with the vendored submodule (classic_control, toy_text); anything
needing extra native deps (box2d, mujoco, ALE) is reported as
browse-only. OpenSpiel comes from the PyPI wheel (pyspiel), pinned to
the same version as the vendored ./open_spiel submodule.

Run tests: uv run python server/test_envs.py
"""

import itertools
import random

from flask import jsonify, request

MAX_SESSIONS = 32          # per session kind; oldest is evicted
PLAYABLE_NAMESPACES = ("classic_control", "toy_text")
SPIEL_MAX_GAME_LEN = 2000  # hard stop for autoplay loops
SPIEL_LOG_CAP = 200

_ids = itertools.count(1)


def _new_sid(prefix):
    return "%s-%d" % (prefix, next(_ids))


def _evict(sessions):
    while len(sessions) > MAX_SESSIONS:
        sessions.pop(next(iter(sessions)))


def _to_jsonable(x):
    """Numpy scalars/arrays and tuples -> plain JSON types."""
    if hasattr(x, "tolist"):
        x = x.tolist()
    if isinstance(x, (list, tuple)):
        return [_to_jsonable(v) for v in x]
    if isinstance(x, float):
        return round(x, 5)
    return x


# Human-readable action names for the common playable envs. Generic
# envs fall back to bare indices; the UI still works.
ACTION_NAMES = {
    "FrozenLake-v1": ["left", "down", "right", "up"],
    "FrozenLake8x8-v1": ["left", "down", "right", "up"],
    "CliffWalking-v1": ["up", "right", "down", "left"],
    "Taxi-v4": ["south", "north", "east", "west", "pickup", "dropoff"],
    "Blackjack-v1": ["stick", "hit"],
    "CartPole-v1": ["push left", "push right"],
    "MountainCar-v0": ["accelerate left", "coast", "accelerate right"],
    "Acrobot-v1": ["torque -1", "torque 0", "torque +1"],
}


# --------------------------------------------------------------------------- #
# Gymnasium sessions
# --------------------------------------------------------------------------- #
ENV_SESSIONS = {}


def _action_space_payload(env, env_id):
    space = env.action_space
    kind = type(space).__name__
    if kind == "Discrete":
        return {"type": "discrete", "n": int(space.n),
                "names": ACTION_NAMES.get(env_id)}
    if kind == "Box":
        return {"type": "box",
                "low": _to_jsonable(space.low), "high": _to_jsonable(space.high),
                "shape": list(space.shape)}
    return {"type": kind.lower()}


def _env_state(sess, reward=0.0, terminated=False, truncated=False):
    env = sess["env"]
    render = None
    if sess["ansi"]:
        try:
            render = env.render()
        except Exception:
            render = None
    return {
        "sid": sess["sid"],
        "envId": sess["envId"],
        "obs": _to_jsonable(sess["obs"]),
        "render": render,
        "reward": round(float(reward), 5),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "done": bool(terminated or truncated),
        "steps": sess["steps"],
        "total": round(sess["total"], 5),
        "actionSpace": sess["actionSpace"],
        "obsSpace": sess["obsSpace"],
    }


def _gym_playable(env_id):
    """Only envs from namespaces that work with the vendored submodule."""
    import gymnasium
    try:
        spec = gymnasium.spec(env_id)
    except Exception:
        return False
    ep = spec.entry_point
    return isinstance(ep, str) and any(("." + ns + ".") in ep or ep.startswith("gymnasium.envs." + ns)
                                       for ns in PLAYABLE_NAMESPACES)


def _sample_action(env):
    a = env.action_space.sample()
    return a


def register_env_api(app):
    @app.post("/api/env/new")
    def env_new():
        import gymnasium
        body = request.get_json(force=True, silent=True) or {}
        env_id = body.get("envId", "")
        if not _gym_playable(env_id):
            return jsonify({"error": "env '%s' is not playable here (namespaces: %s)"
                            % (env_id, ", ".join(PLAYABLE_NAMESPACES))}), 400
        seed = body.get("seed")
        try:
            try:
                env = gymnasium.make(env_id, render_mode="ansi")
                ansi = True
            except Exception:
                env = gymnasium.make(env_id)
                ansi = False
            obs, _info = env.reset(seed=seed)
        except Exception as exc:
            return jsonify({"error": "could not start %s: %s" % (env_id, exc)}), 500
        sid = _new_sid("env")
        ENV_SESSIONS[sid] = {
            "sid": sid, "envId": env_id, "env": env, "ansi": ansi,
            "obs": obs, "steps": 0, "total": 0.0,
            "actionSpace": _action_space_payload(env, env_id),
            "obsSpace": str(env.observation_space),
        }
        _evict(ENV_SESSIONS)
        return jsonify(_env_state(ENV_SESSIONS[sid]))

    @app.post("/api/env/<sid>/step")
    def env_step(sid):
        sess = ENV_SESSIONS.get(sid)
        if not sess:
            return jsonify({"error": "no such session (it may have been evicted)"}), 404
        body = request.get_json(force=True, silent=True) or {}
        env = sess["env"]
        if body.get("policy") == "random":
            action = _sample_action(env)
        elif "action" in body:
            action = body["action"]
            if sess["actionSpace"]["type"] == "discrete":
                try:
                    action = int(action)
                except (TypeError, ValueError):
                    return jsonify({"error": "action must be an integer"}), 400
                if not 0 <= action < sess["actionSpace"]["n"]:
                    return jsonify({"error": "action out of range"}), 400
        else:
            return jsonify({"error": "send {'action': ...} or {'policy': 'random'}"}), 400
        try:
            obs, reward, terminated, truncated, _info = env.step(action)
        except Exception as exc:
            return jsonify({"error": "step failed: %s" % exc}), 500
        sess["obs"] = obs
        sess["steps"] += 1
        sess["total"] += float(reward)
        out = _env_state(sess, reward, terminated, truncated)
        out["action"] = _to_jsonable(action)
        return jsonify(out)

    @app.post("/api/env/<sid>/reset")
    def env_reset(sid):
        sess = ENV_SESSIONS.get(sid)
        if not sess:
            return jsonify({"error": "no such session (it may have been evicted)"}), 404
        body = request.get_json(force=True, silent=True) or {}
        obs, _info = sess["env"].reset(seed=body.get("seed"))
        sess["obs"] = obs
        sess["steps"] = 0
        sess["total"] = 0.0
        return jsonify(_env_state(sess))

    # ----------------------------------------------------------------- #
    # OpenSpiel sessions
    # ----------------------------------------------------------------- #
    @app.post("/api/spiel/new")
    def spiel_new():
        try:
            import pyspiel
        except Exception as exc:
            return jsonify({"error": "pyspiel unavailable: %s" % exc}), 503
        body = request.get_json(force=True, silent=True) or {}
        game_name = body.get("game", "")
        try:
            game = pyspiel.load_game(game_name)
        except Exception as exc:
            return jsonify({"error": "could not load game '%s': %s" % (game_name, exc)}), 400
        seed = body.get("seed")
        rng = random.Random(seed)
        state = game.new_initial_state()
        log = []
        _spiel_resolve_chance(state, rng, log)
        sid = _new_sid("spiel")
        SPIEL_SESSIONS[sid] = {
            "sid": sid, "game": game_name, "gameObj": game, "state": state,
            "rng": rng, "log": log,
            "humanSeat": state.current_player() if not state.is_terminal() else 0,
        }
        _evict(SPIEL_SESSIONS)
        return jsonify(_spiel_state(SPIEL_SESSIONS[sid]))

    @app.post("/api/spiel/<sid>/act")
    def spiel_act(sid):
        sess = SPIEL_SESSIONS.get(sid)
        if not sess:
            return jsonify({"error": "no such session (it may have been evicted)"}), 404
        state = sess["state"]
        if state.is_terminal():
            return jsonify({"error": "game over - start a new one"}), 400
        body = request.get_json(force=True, silent=True) or {}
        if body.get("policy") == "random":
            action = sess["rng"].choice(state.legal_actions())
        elif "action" in body:
            try:
                action = int(body["action"])
            except (TypeError, ValueError):
                return jsonify({"error": "action must be an integer"}), 400
            if action not in state.legal_actions():
                return jsonify({"error": "illegal action %d" % action}), 400
        else:
            return jsonify({"error": "send {'action': ...} or {'policy': 'random'}"}), 400
        _spiel_log(sess, state.current_player(), state.action_to_string(state.current_player(), action))
        state.apply_action(action)
        _spiel_advance(sess)
        return jsonify(_spiel_state(sess))


SPIEL_SESSIONS = {}


def _spiel_log(sess_or_log, player, text):
    log = sess_or_log["log"] if isinstance(sess_or_log, dict) else sess_or_log
    log.append({"p": int(player), "s": text})
    del log[:-SPIEL_LOG_CAP]


def _spiel_resolve_chance(state, rng, log):
    guard = 0
    while state.is_chance_node() and guard < SPIEL_MAX_GAME_LEN:
        outcomes = state.chance_outcomes()
        r, acc = rng.random(), 0.0
        action = outcomes[-1][0]
        for a, p in outcomes:
            acc += p
            if r <= acc:
                action = a
                break
        state.apply_action(action)
        guard += 1


def _spiel_advance(sess):
    """After a human action: resolve chance, then let the random bot
    play every non-human seat until it is the human's turn again (or
    the game ends)."""
    state, rng = sess["state"], sess["rng"]
    guard = 0
    while not state.is_terminal() and guard < SPIEL_MAX_GAME_LEN:
        guard += 1
        if state.is_chance_node():
            _spiel_resolve_chance(state, rng, sess["log"])
            continue
        cur = state.current_player()
        if cur == sess["humanSeat"]:
            break
        action = rng.choice(state.legal_actions())
        _spiel_log(sess, cur, state.action_to_string(cur, action))
        state.apply_action(action)


def _spiel_state(sess):
    state = sess["state"]
    terminal = state.is_terminal()
    human = sess["humanSeat"]
    obs = None
    if not terminal:
        try:
            obs = state.observation_string(human)
        except Exception:
            obs = str(state)
    else:
        obs = str(state)
    legal = []
    if not terminal and state.current_player() == human:
        legal = [{"a": a, "s": state.action_to_string(human, a)}
                 for a in state.legal_actions()]
    return {
        "sid": sess["sid"],
        "game": sess["game"],
        "players": sess["gameObj"].num_players(),
        "humanSeat": human,
        "cur": None if terminal else int(state.current_player()),
        "terminal": terminal,
        "obs": obs,
        "legal": legal,
        "returns": [round(r, 4) for r in state.returns()] if terminal else None,
        "log": sess["log"],
    }
