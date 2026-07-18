"""Tests for the Flask web UI backend."""

from unittest import mock

from absl.testing import absltest

from doppelkopf import cards
from doppelkopf import search
from doppelkopf import web


class WebApiTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    # Advice must be fast and deterministic in tests: no checkpoint.
    patcher = mock.patch.object(search, "resolve_net", lambda *a, **k: None)
    patcher.start()
    self.addCleanup(patcher.stop)
    web.app.config["TESTING"] = True
    self.client = web.app.test_client()

  def new_game(self, **kwargs):
    body = {"seed": 5, "opponents": "heuristic", "advice_worlds": 3}
    body.update(kwargs)
    resp = self.client.post("/api/new", json=body)
    self.assertEqual(resp.status_code, 200)
    data = resp.get_json()
    return data["game"], data["view"]

  def advance_to_human(self, game, view):
    """Steps bots until it is the human's turn (or the game ends)."""
    while not view["terminal"] and not view["your_turn"]:
      resp = self.client.post("/api/step", json={"game": game})
      self.assertEqual(resp.status_code, 200)
      view = resp.get_json()["view"]
    return view

  def test_new_game_view_shape(self):
    game, view = self.new_game()
    self.assertLen(view["hand"], cards.CARDS_PER_PLAYER)
    self.assertEqual(view["hand_sizes"], [12, 12, 12, 12])
    self.assertEqual(view["trick_no"], 1)
    self.assertFalse(view["terminal"])
    self.assertEqual(view["names"][0], "You")
    self.assertIsInstance(view["you_re"], bool)
    self.assertEqual(view["points_taken"], [0, 0, 0, 0])
    # State endpoint returns the same picture.
    resp = self.client.get(f"/api/state?game={game}")
    self.assertEqual(resp.status_code, 200)
    self.assertEqual(resp.get_json()["view"]["hand"], view["hand"])

  def test_unknown_game_is_404(self):
    resp = self.client.get("/api/state?game=nope")
    self.assertEqual(resp.status_code, 404)

  def test_bad_opponents_is_400(self):
    resp = self.client.post("/api/new", json={"opponents": "cheater"})
    self.assertEqual(resp.status_code, 400)

  def test_play_out_of_turn_or_illegal_is_400(self):
    game, view = self.new_game()
    if not view["your_turn"]:
      # Not our turn: playing anything is rejected.
      resp = self.client.post("/api/play",
                              json={"game": game, "card": 0})
      self.assertEqual(resp.status_code, 400)
      view = self.advance_to_human(game, view)
    # Our turn now: a card type we do not hold is rejected.
    held = {card["id"] for card in view["hand"]}
    missing = next(c for c in range(cards.NUM_CARD_TYPES)
                   if c not in held)
    resp = self.client.post("/api/play",
                            json={"game": game, "card": missing})
    self.assertEqual(resp.status_code, 400)
    resp = self.client.post("/api/play",
                            json={"game": game, "card": "QC"})
    self.assertEqual(resp.status_code, 400)

  def test_advice_ranks_exactly_the_legal_cards(self):
    game, view = self.new_game()
    view = self.advance_to_human(game, view)
    resp = self.client.get(f"/api/advice?game={game}")
    self.assertEqual(resp.status_code, 200)
    data = resp.get_json()
    legal = {card["id"] for card in view["hand"] if card["legal"]}
    self.assertCountEqual([a["card"]["id"] for a in data["advice"]], legal)
    scores = [a["score"] for a in data["advice"]]
    self.assertEqual(scores, sorted(scores, reverse=True))
    self.assertEqual(data["source"], "heuristic")
    # Playing the recommended card works.
    best = data["advice"][0]["card"]["id"]
    resp = self.client.post("/api/play", json={"game": game, "card": best})
    self.assertEqual(resp.status_code, 200)

  def test_advice_off_turn_is_400(self):
    game, view = self.new_game()
    if view["your_turn"]:
      self.skipTest("human leads for this seed")
    resp = self.client.get(f"/api/advice?game={game}")
    self.assertEqual(resp.status_code, 400)

  def test_step_on_human_turn_is_400(self):
    game, view = self.new_game()
    view = self.advance_to_human(game, view)
    resp = self.client.post("/api/step", json={"game": game})
    self.assertEqual(resp.status_code, 400)

  def test_full_game_reaches_consistent_result(self):
    game, view = self.new_game(seed=17)
    for _ in range(cards.NUM_CARDS + 8):
      if view["terminal"]:
        break
      if view["your_turn"]:
        first_legal = next(card["id"] for card in view["hand"]
                           if card["legal"])
        resp = self.client.post(
            "/api/play", json={"game": game, "card": first_legal})
      else:
        resp = self.client.post("/api/step", json={"game": game})
      self.assertEqual(resp.status_code, 200)
      view = resp.get_json()["view"]
    self.assertTrue(view["terminal"])
    result = view["result"]
    self.assertEqual(result["re_points"] + result["kontra_points"],
                     cards.TOTAL_POINTS)
    self.assertEqual(sum(result["returns"]), 0)
    self.assertLen(view["tricks"], cards.NUM_TRICKS)
    self.assertEqual(view["hand_sizes"], [0, 0, 0, 0])
    self.assertCountEqual(result["re_seats"] + result["kontra_seats"],
                          [0, 1, 2, 3])


if __name__ == "__main__":
  absltest.main()
