"""Web UI for Doppelkopf: play against bots with master-bot advice.

A small Flask app; all game state lives server-side. The human sits at
seat 0 against three bots (rule-based or the PIMC master bot). The
advice endpoint asks the strongest available advisor -- PIMC search
using the trained policy net from `checkpoints/master.npz` when it
exists -- to rank the human's legal cards by expected score.

Run from the open_spiel repository root:

    ../.venv/bin/python -m doppelkopf.web            # http://127.0.0.1:8360
    ../.venv/bin/python -m doppelkopf.web --port 9000
"""

import argparse
import random
import secrets
import threading

from flask import Flask, jsonify, request

from doppelkopf import cards
from doppelkopf import scoring
from doppelkopf import search
from doppelkopf.bots import HeuristicBot
from doppelkopf.game import legal_cards
from doppelkopf.train import deal

HUMAN = 0
PLAYER_NAMES = ["You", "West", "North", "East"]

app = Flask(__name__, static_folder="static", static_url_path="/static")

_games = {}
_lock = threading.Lock()


class GameSession:
  """One table: state, opponent bots, advisor, rng."""

  def __init__(self, seed=None, opponents="heuristic", advice_worlds=24):
    self.rng = random.Random(seed)
    self.state = deal(self.rng)
    self.net = search.resolve_net()
    self.advisor = search.PIMCAdvisor(
        num_worlds=advice_worlds, net=self.net,
        rng=random.Random(self.rng.random()))
    if opponents == "master":
      self.bots = {
          p: search.MasterBot(p, search.PIMCAdvisor(
              num_worlds=12, net=self.net,
              rng=random.Random(self.rng.random())))
          for p in range(1, cards.NUM_PLAYERS)
      }
    else:
      self.bots = {p: HeuristicBot(p, random.Random(self.rng.random()))
                   for p in range(1, cards.NUM_PLAYERS)}
    self.opponents = opponents
    self.last_play = None  # {"seat": s, "card": c} of the latest move.
    self.advice_cache = None  # Advice for the current decision, if any.

  # --- Serialization ---

  def card_json(self, c, legal=None):
    return {
        "id": c,
        "rank": cards.RANK_LETTERS[cards.rank_of(c)],
        "suit": cards.suit_of(c),
        "trump": cards.is_trump(c),
        "points": cards.card_points(c),
        "legal": (c in legal) if legal is not None else None,
    }

  def view(self):
    state = self.state
    terminal = state.is_terminal()
    to_act = None if terminal else state.current_player()
    legal = None
    if to_act == HUMAN:
      legal = set(legal_cards(state.hands[HUMAN], state.current_trick))

    hand = []
    for c in range(cards.NUM_CARD_TYPES):
      hand.extend([c] * state.hands[HUMAN][c])
    hand = [self.card_json(c, legal if legal is not None else set())
            for c in cards.sort_for_display(hand)]

    trick = []
    for i, c in enumerate(state.current_trick):
      seat = (state.trick_leader + i) % cards.NUM_PLAYERS
      trick.append({"seat": seat, "card": self.card_json(c)})

    tricks = []
    for t in state.tricks:
      tricks.append({
          "leader": t.leader,
          "winner": t.winner,
          "points": t.points,
          "cards": [{"seat": t.player_of(i), "card": self.card_json(c)}
                    for i, c in enumerate(t.cards)],
      })

    view = {
        "names": PLAYER_NAMES,
        "opponents": self.opponents,
        "advice_source": "net" if self.net else "heuristic",
        "hand": hand,
        "hand_sizes": [sum(state.hands[p]) for p in range(cards.NUM_PLAYERS)],
        "current_trick": trick,
        "trick_leader": state.trick_leader,
        "trick_no": min(len(state.tricks) + 1, cards.NUM_TRICKS),
        "to_act": to_act,
        "your_turn": to_act == HUMAN,
        "terminal": terminal,
        "points_taken": state.points_taken(),
        "known_re": sorted(state.known_re_players()),
        "you_re": HUMAN in state.re_players,
        "silent_wedding": (HUMAN in state.re_players
                           and len(state.re_players) == 1),
        "last_play": self.last_play,
        "last_trick": tricks[-1] if tricks else None,
        "tricks": tricks,
    }
    if terminal:
      res = scoring.compute_result(state.re_players, state.tricks)
      view["result"] = {
          "re_seats": sorted(state.re_players),
          "kontra_seats": sorted(set(range(cards.NUM_PLAYERS))
                                 - state.re_players),
          "re_points": res["re_points"],
          "kontra_points": res["kontra_points"],
          "re_wins": res["re_wins"],
          "base": res["base"],
          "specials": res["specials"],
          "value": res["value"],
          "returns": res["returns"],
      }
    return view

  # --- Moves ---

  def play_human(self, card):
    state = self.state
    if state.is_terminal() or state.current_player() != HUMAN:
      raise ValueError("it is not your turn")
    legal = legal_cards(state.hands[HUMAN], state.current_trick)
    if card not in legal:
      raise ValueError("that card is not playable here (follow suit)")
    state.apply_action(card)
    self.last_play = {"seat": HUMAN, "card": self.card_json(card)}
    self.advice_cache = None

  def step_bot(self):
    state = self.state
    seat = state.current_player()
    if state.is_terminal() or seat == HUMAN:
      raise ValueError("no bot to move")
    card = self.bots[seat].step(state)
    state.apply_action(card)
    self.last_play = {"seat": seat, "card": self.card_json(card)}
    self.advice_cache = None

  def advice(self):
    state = self.state
    if state.is_terminal() or state.current_player() != HUMAN:
      raise ValueError("advice is only available on your turn")
    if self.advice_cache is None:
      scores = self.advisor.evaluate(state, HUMAN)
      self.advice_cache = [
          {"card": self.card_json(c), "score": round(s, 2)}
          for c, s in scores
      ]
    return self.advice_cache


def _session():
  game_id = request.args.get("game") or (request.get_json(silent=True)
                                         or {}).get("game")
  with _lock:
    session = _games.get(game_id)
  if session is None:
    raise KeyError("unknown game id; start a new game")
  return session


@app.errorhandler(ValueError)
def _bad_request(err):
  return jsonify({"error": str(err)}), 400


@app.errorhandler(KeyError)
def _not_found(err):
  return jsonify({"error": err.args[0] if err.args else "not found"}), 404


@app.route("/")
def index():
  return app.send_static_file("index.html")


@app.route("/api/new", methods=["POST"])
def api_new():
  body = request.get_json(silent=True) or {}
  seed = body.get("seed")
  if seed is not None:
    seed = int(seed)
  opponents = body.get("opponents", "heuristic")
  if opponents not in ("heuristic", "master"):
    raise ValueError("opponents must be 'heuristic' or 'master'")
  advice_worlds = int(body.get("advice_worlds", 24))
  session = GameSession(seed=seed, opponents=opponents,
                        advice_worlds=advice_worlds)
  game_id = secrets.token_hex(8)
  with _lock:
    if len(_games) > 200:  # Drop the oldest tables, keep memory bounded.
      for key in list(_games)[:100]:
        del _games[key]
    _games[game_id] = session
  return jsonify({"game": game_id, "view": session.view()})


@app.route("/api/state")
def api_state():
  return jsonify({"view": _session().view()})


@app.route("/api/play", methods=["POST"])
def api_play():
  session = _session()
  body = request.get_json(silent=True) or {}
  card = body.get("card")
  if not isinstance(card, int) or not 0 <= card < cards.NUM_CARD_TYPES:
    raise ValueError("card must be an int in [0, 24)")
  session.play_human(card)
  return jsonify({"view": session.view()})


@app.route("/api/step", methods=["POST"])
def api_step():
  session = _session()
  session.step_bot()
  return jsonify({"view": session.view()})


@app.route("/api/advice")
def api_advice():
  session = _session()
  return jsonify({"advice": session.advice(),
                  "source": session.view()["advice_source"]})


def main():
  parser = argparse.ArgumentParser(description="Doppelkopf web UI.")
  parser.add_argument("--host", default="127.0.0.1")
  parser.add_argument("--port", type=int, default=8360)
  parser.add_argument("--debug", action="store_true")
  args = parser.parse_args()
  print(f"Doppelkopf web UI on http://{args.host}:{args.port}")
  app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
  main()
