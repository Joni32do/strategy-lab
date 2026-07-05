"""A tiny HTTP bridge between the `high-level` terminal app and catanatron.

The Rust Catan lens (`src/catan/`) speaks a small JSON API over loopback; this
server answers it by driving the real catanatron engine. It has no third-party
web dependency on purpose -- it is plain `http.server`, so the only thing to
install is catanatron itself.

Endpoints (all JSON):
  GET  /api/defaults              -> opponents + slider ranges
  POST /api/simulate              -> aggregate result of N games
  POST /api/game                  -> start a step-through game
  POST /api/game/<id>/tick        -> advance that game by one ply

Run it:  python3 app.py   (listens on 127.0.0.1:8000)
"""

from __future__ import annotations

import json
import sys
import uuid
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from catanatron import Game, Color, RandomPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer
from catanatron.players.value import ValueFunctionPlayer
from catanatron.players.minimax import AlphaBetaPlayer
from catanatron.state_functions import (
    get_actual_victory_points,
    get_visible_victory_points,
    get_player_freqdeck,
    get_dev_cards_in_hand,
    get_longest_road_length,
)

import policy
from policy import MetricPlayer, Weights, TradeParams

HOST, PORT = "127.0.0.1", 8000

YOU = Color.RED
OPP = Color.BLUE

OPPONENTS = ["RANDOM", "WEIGHTED", "VALUE", "ALPHABETA", "MIRROR"]

# Slider ranges the terminal syncs to (key -> [min, max]); these mirror the
# Rust-side defaults so a sync is a no-op unless we change our mind here.
RANGES = {
    "vp": [0.0, 1.0], "production": [0.0, 1.0], "expansion": [0.0, 1.0],
    "prod_norm": [4.0, 24.0], "expansion_norm": [2.0, 16.0],
    "lam_max": [0.0, 5.0], "lam_steepness": [1.0, 20.0], "lam_midpoint": [0.0, 1.0],
    "veto_vp_margin": [0.0, 4.0], "margin": [0.0, 2.0], "premium_per_vp": [0.0, 2.0],
    "scarcity_weight": [0.0, 3.0], "need_weight": [0.0, 4.0], "base_value": [0.0, 2.0],
}

GAMES = {}  # game_id -> {"game", "players", "you"}


# --------------------------------------------------------------------------- #
# building players / games
# --------------------------------------------------------------------------- #
def make_opponent(name, weights, trade, enable_trade):
    name = (name or "VALUE").upper()
    if name == "RANDOM":
        return RandomPlayer(OPP)
    if name == "WEIGHTED":
        return WeightedRandomPlayer(OPP)
    if name == "ALPHABETA":
        return AlphaBetaPlayer(OPP, 2, True)
    if name == "MIRROR":
        return MetricPlayer(OPP, weights=weights, trade=trade, enable_trade=enable_trade)
    return ValueFunctionPlayer(OPP)


def build_game(body, seed):
    weights = Weights.from_json(body.get("weights"))
    trade = TradeParams.from_json(body.get("trade"))
    enable_trade = bool(body.get("enable_trade", True))
    you = MetricPlayer(YOU, weights=weights, trade=trade, enable_trade=enable_trade)
    opp = make_opponent(body.get("opponent"), weights, trade, enable_trade)
    game = Game(players=[you, opp], seed=seed)
    return game, you, opp, weights


# --------------------------------------------------------------------------- #
# serialization (shapes must match src/catan/mod.rs parsers)
# --------------------------------------------------------------------------- #
def jsonify(v):
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (list, tuple)):
        return [jsonify(x) for x in v]
    return v


def serialize_action(action):
    return {
        "by": jsonify(action.color),
        "type": jsonify(action.action_type),
        "value": jsonify(action.value),
    }


def serialize_state(game, weights):
    state = game.state
    board = state.board
    cmap = board.map

    tiles_sorted = sorted(cmap.land_tiles.values(), key=lambda t: t.id)
    id_to_index = {t.id: i for i, t in enumerate(tiles_sorted)}
    tiles = [
        {
            "resource": (t.resource.lower() if t.resource else "desert"),
            "number": t.number,
        }
        for t in tiles_sorted
    ]

    robber_index = None
    try:
        robber_tile = cmap.land_tiles[board.robber_coordinate]
        robber_index = id_to_index.get(robber_tile.id)
    except Exception:
        robber_index = None

    players = []
    for color in state.colors:
        players.append(
            {
                "color": color.value,
                "is_you": color == YOU,
                "vp": get_actual_victory_points(state, color),
                "public_vp": get_visible_victory_points(state, color),
                "hand": get_player_freqdeck(state, color),
                "dev_cards": get_dev_cards_in_hand(state, color),
                "longest_road": get_longest_road_length(state, color),
                "strength": round(policy.strength(state, color, weights, game.vps_to_win), 3),
            }
        )

    buildings = {
        str(node): [color.value, btype]
        for node, (color, btype) in board.buildings.items()
    }
    roads = [[a, b, color.value] for (a, b), color in board.roads.items()]

    winner = game.winning_color()
    prompt = ""
    if game.playable_actions:
        prompt = jsonify(game.playable_actions[0].action_type)

    return {
        "tiles": tiles,
        "robber_tile": robber_index,
        "buildings": buildings,
        "roads": roads,
        "players": players,
        "current_color": state.current_color().value,
        "prompt": prompt,
        "num_turns": state.num_turns,
        "winner": winner.value if winner else None,
    }


# --------------------------------------------------------------------------- #
# endpoint handlers
# --------------------------------------------------------------------------- #
def handle_defaults():
    return {"opponents": OPPONENTS, "ranges": RANGES}


def handle_simulate(body):
    n = int(body.get("n", 20))
    seed0 = int(body.get("seed", 0))
    opponent = body.get("opponent", "VALUE")

    you_wins = opp_wins = draws = 0
    total_turns = your_vp = opp_vp = 0
    maritime = 0

    for i in range(n):
        game, you, opp, weights = build_game(body, seed0 + i)
        winner = game.play()
        total_turns += game.state.num_turns
        your_vp += get_actual_victory_points(game.state, YOU)
        opp_vp += get_actual_victory_points(game.state, OPP)
        maritime += you.maritime_trades
        if winner == YOU:
            you_wins += 1
        elif winner == OPP:
            opp_wins += 1
        else:
            draws += 1

    n_safe = max(1, n)
    return {
        "games": n,
        "opponent": opponent,
        "you_wins": you_wins,
        "opp_wins": opp_wins,
        "draws": draws,
        "you_winrate": you_wins / n_safe,
        "avg_turns": total_turns / n_safe,
        "avg_your_vp": your_vp / n_safe,
        "avg_opp_vp": opp_vp / n_safe,
        # Domestic (player-to-player) negotiation is simplified to maritime
        # trades in this bridge, so only the offer/accept counters are live.
        "trades": {
            "offers": maritime, "accepts": maritime, "rejects": 0,
            "confirms": maritime, "cancels": 0, "vetoes": 0,
        },
    }


def handle_new_game(body):
    seed = int(body.get("seed", 0)) or abs(hash(uuid.uuid4())) % 1_000_000
    game, you, opp, weights = build_game(body, seed)
    gid = uuid.uuid4().hex[:8]
    GAMES[gid] = {"game": game, "you": you, "weights": weights}
    return {"game_id": gid, "seed": seed, "state": serialize_state(game, weights)}


def handle_tick(gid):
    entry = GAMES.get(gid)
    if entry is None:
        return None, 404, {"error": f"no such game {gid}"}
    game = entry["game"]
    you = entry["you"]
    weights = entry["weights"]

    if game.winning_color() is not None or game.state.num_turns >= 1000:
        return {
            "actor": None, "action": None, "explanation": None,
            "state": serialize_state(game, weights), "done": True,
        }, 200, None

    actor = game.state.current_color()
    record = game.play_tick()
    action = record.action if record is not None else None

    if actor == YOU:
        explanation = you.last_explanation or {"kind": "value", "note": ""}
    else:
        explanation = {"kind": "opponent", "note": actor.value.lower()}

    done = game.winning_color() is not None
    return {
        "actor": actor.value,
        "action": serialize_action(action) if action else None,
        "explanation": explanation,
        "state": serialize_state(game, weights),
        "done": done,
    }, 200, None


# --------------------------------------------------------------------------- #
# HTTP plumbing
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 (the default) closes the connection after each response, which is
    # exactly what the Rust client's read-to-EOF expects.
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):  # keep the terminal quiet
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/api/defaults":
            self._send(handle_defaults())
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        try:
            if self.path == "/api/simulate":
                self._send(handle_simulate(self._read_body()))
            elif self.path == "/api/game":
                self._send(handle_new_game(self._read_body()))
            elif self.path.startswith("/api/game/") and self.path.endswith("/tick"):
                gid = self.path[len("/api/game/"):-len("/tick")]
                obj, status, err = handle_tick(gid)
                self._send(err if err else obj, status)
            else:
                self._send({"error": "not found"}, 404)
        except Exception as e:  # never take the TUI down; report the error
            self._send({"error": f"{type(e).__name__}: {e}"}, 500)


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT
    print(f"catanatron bridge listening on http://{host}:{port}")
    print("  GET  /api/defaults   POST /api/simulate   POST /api/game   POST /api/game/<id>/tick")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
