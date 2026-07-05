"""
Flask wrapper around catanatron. The browser client (js/catan-lab.js) is a thin
shell: every Catan rule, every legal-move check, every game tick is computed by
the catanatron engine here. This server only:

  - configures players (your StrategicTradingPlayer vs a chosen opponent),
  - runs games / single ticks,
  - serializes the live state and the policy's reasoning for rendering.

Run:  uv run python server/app.py   (serves the whole app at :8000)
"""
import os
import random
import uuid

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from catanatron.game import Game
from catanatron.models.player import RandomPlayer, Color
from catanatron.players.value import ValueFunctionPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

try:
    from catanatron.players.minimax import AlphaBetaPlayer
except Exception:  # optional / heavier
    AlphaBetaPlayer = None

try:
    from catanatron.players.mcts import MCTSPlayer
except Exception:  # optional / heavier
    MCTSPlayer = None

from catanatron.state_functions import (
    get_actual_victory_points,
    get_visible_victory_points,
    get_player_freqdeck,
    get_longest_road_length,
    player_num_dev_cards,
)
from catanatron.models.enums import SETTLEMENT, CITY

from policy import (
    StrategicTradingPlayer,
    MetricWeights,
    TradeParams,
    position_strength,
    _action_str,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, static_folder=None)
CORS(app)

GAMES = {}  # game_id -> dict(game, you_color, weights, tp, players)


# --------------------------------------------------------------------------- #
# Player wiring
# --------------------------------------------------------------------------- #
def make_opponent(kind, color):
    kind = (kind or "VALUE").upper()
    if kind == "RANDOM":
        return RandomPlayer(color)
    if kind == "WEIGHTED":
        return WeightedRandomPlayer(color)
    if kind == "ALPHABETA" and AlphaBetaPlayer is not None:
        return AlphaBetaPlayer(color, 2, True)
    if kind == "MCTS" and MCTSPlayer is not None:
        return MCTSPlayer(color, num_simulations=25)  # kept low so batches stay usable
    if kind == "TRADER":
        return StrategicTradingPlayer(color)  # mirror match
    return ValueFunctionPlayer(color)


def opponent_kinds():
    kinds = ["RANDOM", "WEIGHTED", "VALUE"]
    if AlphaBetaPlayer is not None:
        kinds.append("ALPHABETA")
    if MCTSPlayer is not None:
        kinds.append("MCTS")
    kinds.append("TRADER")
    return kinds


def build_players(weights, tp, opponent_kind, enable_trade, you_first, base_bot="VALUE"):
    you = StrategicTradingPlayer(
        Color.RED if you_first else Color.BLUE,
        weights=weights,
        trade_params=tp,
        enable_trade=enable_trade,
        base_bot=base_bot,
    )
    opp = make_opponent(opponent_kind, Color.BLUE if you_first else Color.RED)
    players = [you, opp] if you_first else [opp, you]
    return players, you, opp


# --------------------------------------------------------------------------- #
# Serialization (compact; geometry already lives in js/games/catan-board.js)
# --------------------------------------------------------------------------- #
def serialize_state(game, you_color, weights):
    state = game.state
    board = state.board

    land = list(board.map.land_tiles.items())
    tiles = [{"resource": t.resource, "number": t.number} for _c, t in land]
    robber_tile = next(
        (i for i, (c, _t) in enumerate(land) if c == board.robber_coordinate), None
    )

    buildings = {
        str(node): {"color": color.value, "type": btype}
        for node, (color, btype) in board.buildings.items()
    }
    seen = set()
    roads = []
    for (a, b), color in board.roads.items():
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        roads.append({"edge": [key[0], key[1]], "color": color.value})

    players = []
    for color in state.colors:
        strength, breakdown = position_strength(game, color, weights)
        players.append(
            {
                "color": color.value,
                "is_you": color == you_color,
                "vp": get_actual_victory_points(state, color),
                "public_vp": get_visible_victory_points(state, color),
                "hand": get_player_freqdeck(state, color),
                "dev_cards": player_num_dev_cards(state, color),
                "longest_road": get_longest_road_length(state, color),
                "strength": round(strength, 3),
                "strength_detail": {k: round(v, 3) if isinstance(v, float) else v
                                    for k, v in breakdown.items()},
            }
        )

    return {
        "tiles": tiles,
        "robber_tile": robber_tile,
        "buildings": buildings,
        "roads": roads,
        "players": players,
        "current_color": state.current_color().value,
        "prompt": state.current_prompt.name,
        "num_turns": state.num_turns,
        "is_resolving_trade": state.is_resolving_trade,
        "winner": game.winning_color().value if game.winning_color() else None,
    }


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/defaults")
def defaults():
    w, tp = MetricWeights(), TradeParams()
    from dataclasses import asdict

    return jsonify(
        {
            "weights": asdict(w),
            "trade": asdict(tp),
            "opponents": opponent_kinds(),
            "base_bots": ["VALUE"] + (["ALPHABETA"] if AlphaBetaPlayer else []),
            "ranges": {
                "vp": [0, 1], "production": [0, 1], "expansion": [0, 1],
                "prod_norm": [4, 24], "expansion_norm": [2, 16], "block_weight": [0, 3],
                "lam_max": [0, 5], "lam_steepness": [1, 20], "lam_midpoint": [0, 1],
                "veto_vp_margin": [0, 4], "margin": [0, 2], "premium_per_vp": [0, 2],
                "scarcity_weight": [0, 3], "need_weight": [0, 4], "base_value": [0, 2],
            },
        }
    )


@app.post("/api/simulate")
def simulate():
    body = request.get_json(force=True) or {}
    n = max(1, min(int(body.get("n", 50)), 300))
    seed0 = int(body.get("seed", 0))
    weights = MetricWeights.from_dict(body.get("weights"))
    tp = TradeParams.from_dict(body.get("trade"))
    opponent = body.get("opponent", "VALUE")
    enable_trade = bool(body.get("enable_trade", True))
    base_bot = body.get("base_bot", "VALUE")

    you_wins = opp_wins = draws = 0
    your_vp_sum = opp_vp_sum = turns_sum = 0
    agg = {"offers": 0, "accepts": 0, "rejects": 0, "confirms": 0,
           "cancels": 0, "vetoes": 0, "blocks": 0}

    for i in range(n):
        random.seed(seed0 + i)
        players, you, _opp = build_players(
            weights, tp, opponent, enable_trade, you_first=(i % 2 == 0), base_bot=base_bot
        )
        game = Game(players)
        winner = game.play()
        for k in agg:
            agg[k] += you.stats[k]
        your_vp_sum += get_actual_victory_points(game.state, you.color)
        opp_color = next(c for c in game.state.colors if c != you.color)
        opp_vp_sum += get_actual_victory_points(game.state, opp_color)
        turns_sum += game.state.num_turns
        if winner == you.color:
            you_wins += 1
        elif winner is None:
            draws += 1
        else:
            opp_wins += 1

    return jsonify(
        {
            "games": n,
            "opponent": opponent,
            "you_wins": you_wins,
            "opp_wins": opp_wins,
            "draws": draws,
            "you_winrate": round(you_wins / n, 4),
            "avg_turns": round(turns_sum / n, 1),
            "avg_your_vp": round(your_vp_sum / n, 2),
            "avg_opp_vp": round(opp_vp_sum / n, 2),
            "trades": agg,
        }
    )


@app.post("/api/game")
def new_game():
    body = request.get_json(force=True) or {}
    weights = MetricWeights.from_dict(body.get("weights"))
    tp = TradeParams.from_dict(body.get("trade"))
    opponent = body.get("opponent", "VALUE")
    enable_trade = bool(body.get("enable_trade", True))
    base_bot = body.get("base_bot", "VALUE")
    seed = int(body.get("seed", random.randrange(10_000_000)))
    random.seed(seed)

    players, you, _opp = build_players(
        weights, tp, opponent, enable_trade, you_first=True, base_bot=base_bot
    )
    game = Game(players)
    gid = str(uuid.uuid4())[:8]
    GAMES[gid] = {"game": game, "you": you, "weights": weights, "tp": tp, "seed": seed}
    return jsonify({"game_id": gid, "seed": seed, "state": serialize_state(game, you.color, weights)})


@app.post("/api/game/<gid>/tick")
def tick(gid):
    entry = GAMES.get(gid)
    if entry is None:
        return jsonify({"error": "unknown game"}), 404
    game, you, weights = entry["game"], entry["you"], entry["weights"]

    if game.winning_color() is not None:
        return jsonify({"done": True, "action": None, "explanation": None,
                        "state": serialize_state(game, you.color, weights)})

    actor = game.state.current_player()
    record = game.play_tick()
    explanation = getattr(actor, "last_explanation", None)
    if explanation is None:
        explanation = {"kind": "play", "note": f"{type(actor).__name__} move",
                       "action": _action_str(record.action)}

    return jsonify(
        {
            "done": game.winning_color() is not None,
            "actor": actor.color.value,
            "actor_is_you": actor.color == you.color,
            "action": _action_str(record.action),
            "explanation": explanation,
            "state": serialize_state(game, you.color, weights),
        }
    )


# --------------------------------------------------------------------------- #
# Static hosting (serve the whole strategy-lab so one command runs everything)
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return send_from_directory(ROOT, "catan.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(ROOT, path)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
