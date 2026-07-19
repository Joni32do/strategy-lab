"""Tests for the Python Doppelkopf game."""

from absl.testing import absltest

import pyspiel

import doppelkopf.game  # noqa: F401  (registers python_doppelkopf)
from doppelkopf import cards
from doppelkopf import scoring
from doppelkopf.game import legal_cards


def c(name):
  """Card type from a name like 'QC' or '10H'."""
  rank, suit = name[:-1], name[-1]
  return cards.make_card(
      cards.SUIT_LETTERS.index(suit), cards.RANK_LETTERS.index(rank))


class CardsTest(absltest.TestCase):

  def test_deck_points_total_240(self):
    total = 2 * sum(cards.card_points(card)
                    for card in range(cards.NUM_CARD_TYPES))
    self.assertEqual(total, cards.TOTAL_POINTS)

  def test_trump_count_and_order(self):
    self.assertLen(cards.TRUMP_ORDER, 13)
    self.assertTrue(cards.beats(c("10H"), c("QC")))    # Dulle on top.
    self.assertTrue(cards.beats(c("QC"), c("QS")))
    self.assertTrue(cards.beats(c("QD"), c("JC")))
    self.assertTrue(cards.beats(c("JD"), c("AD")))     # Jacks over aces.
    self.assertTrue(cards.beats(c("9D"), c("AS")))     # Any trump beats plain.
    self.assertFalse(cards.beats(c("AS"), c("9D")))

  def test_plain_suit_order_and_first_wins_ties(self):
    self.assertTrue(cards.beats(c("AS"), c("10S")))
    self.assertTrue(cards.beats(c("10S"), c("KS")))
    self.assertTrue(cards.beats(c("KS"), c("9S")))
    # Identical cards: the incumbent (first-played) wins.
    self.assertFalse(cards.beats(c("QC"), c("QC")))
    # Off-suit plain cards never win.
    self.assertFalse(cards.beats(c("AH"), c("9S")))

  def test_trick_winner(self):
    self.assertEqual(cards.trick_winner_offset(
        [c("AS"), c("10S"), c("9D"), c("KS")]), 2)  # Trump takes it.
    self.assertEqual(cards.trick_winner_offset(
        [c("9H"), c("AH"), c("KH"), c("AH")]), 1)   # First ace of two.

  def test_second_dulle_rule(self):
    # By default (rulebook special rule on) the later Dulle wins; when
    # the rule is off the first-played Dulle keeps the trick. The rule
    # is specific to the Dulle: other doubled trumps still go to the
    # first-played copy.
    self.assertTrue(cards.beats(c("10H"), c("10H")))                  # on
    self.assertFalse(cards.beats(c("10H"), c("10H"), second_dulle=False))
    self.assertFalse(cards.beats(c("QC"), c("QC")))                   # not a Dulle
    two_dullen = [c("10H"), c("JC"), c("10H"), c("9D")]
    self.assertEqual(cards.trick_winner_offset(two_dullen), 2)        # second
    self.assertEqual(
        cards.trick_winner_offset(two_dullen, second_dulle=False), 0)

  def test_follow_suit(self):
    hand = [0] * cards.NUM_CARD_TYPES
    for name in ("QC", "9D", "AS", "9H"):
      hand[c(name)] += 1
    # Trump led: must play one of the trumps.
    self.assertCountEqual(legal_cards(hand, [c("JD")]), [c("QC"), c("9D")])
    # Spades led: must play the spade.
    self.assertCountEqual(legal_cards(hand, [c("KS")]), [c("AS")])
    # Diamonds-as-plain does not exist: 9D follows trump, not AS.
    self.assertCountEqual(legal_cards(hand, [c("10D")]), [c("QC"), c("9D")])
    # Clubs led, none in hand: anything goes.
    self.assertCountEqual(
        legal_cards(hand, [c("AC")]),
        [c("QC"), c("9D"), c("AS"), c("9H")])


class GameApiTest(absltest.TestCase):

  def test_random_sim(self):
    game = pyspiel.load_game("python_doppelkopf")
    pyspiel.random_sim_test(game, num_sims=20, serialize=False, verbose=False)


# A fully scripted game: seat 0 is dealt the twelve highest trumps
# (including both club queens -> silent wedding) and wins every trick.
_HANDS = [
    ["10H", "10H", "QC", "QC", "QS", "QS", "QH", "QH", "QD", "QD", "JC", "JC"],
    ["JS", "JS", "AD", "AD", "AC", "AC", "10C", "10C", "KC", "KC", "9C", "9C"],
    ["JH", "JH", "10D", "10D", "AS", "AS", "10S", "10S", "KS", "KS", "9S", "9S"],
    ["JD", "JD", "KD", "KD", "9D", "9D", "AH", "AH", "KH", "KH", "9H", "9H"],
]
_TRICKS = [
    ["10H", "JS", "JH", "JD"],
    ["10H", "JS", "JH", "JD"],
    ["QC", "AD", "10D", "KD"],   # Both foxes fall to Re...
    ["QC", "AD", "10D", "KD"],
    ["QS", "AC", "AS", "9D"],
    ["QS", "AC", "AS", "9D"],
    ["QH", "10C", "10S", "AH"],
    ["QH", "10C", "10S", "AH"],
    ["QD", "KC", "KS", "KH"],
    ["QD", "KC", "KS", "KH"],
    ["JC", "9C", "9S", "9H"],
    ["JC", "9C", "9S", "9H"],    # ...and a karlchen to finish.
]


class ScriptedGameTest(absltest.TestCase):

  def test_silent_wedding_schwarz(self):
    game = pyspiel.load_game("python_doppelkopf")
    state = game.new_initial_state()
    for hand in _HANDS:
      for name in hand:
        self.assertTrue(state.is_chance_node())
        state.apply_action(c(name))
    self.assertEqual(state.re_players, {0})

    # Seat 1 holds only two trump types and must follow the trump lead.
    state_probe = state.child(c("10H"))
    self.assertCountEqual(state_probe.legal_actions(1), [c("JS"), c("AD")])

    for trick in _TRICKS:
      for name in trick:
        state.apply_action(c(name))
    self.assertTrue(state.is_terminal())

    result = state.result()
    self.assertEqual(result["re_points"], 240)
    self.assertTrue(result["re_wins"])
    self.assertCountEqual(
        [label for label, _ in result["base"]],
        ["won", "no 90", "no 60", "no 30", "schwarz"])
    self.assertCountEqual(
        result["specials"],
        [("fox caught", 1), ("fox caught", 1), ("karlchen", 1)])
    self.assertEqual(result["value"], 8)
    # Silent wedding: the soloist collects triple, zero-sum overall.
    self.assertEqual(state.returns(), [24.0, -8.0, -8.0, -8.0])


class ScoringTest(absltest.TestCase):

  def test_kontra_sweep_with_specials_against_re(self):
    # Score the scripted tricks (all won by seat 0) with seats 1 and 2
    # as Re: now Kontra sweeps, and the special points go against Re.
    tricks = [scoring.Trick(0, [c(n) for n in names]) for names in _TRICKS]
    result = scoring.compute_result({1, 2}, tricks)
    self.assertFalse(result["re_wins"])
    self.assertEqual(result["kontra_points"], 240)
    labels = [label for label, _ in result["base"]]
    self.assertIn("against the queens", labels)
    self.assertIn("schwarz", labels)
    # Foxes belonged to seat 1 (Re), captured by seat 0 (Kontra).
    self.assertCountEqual(
        result["specials"],
        [("fox caught", -1), ("fox caught", -1), ("karlchen", -1)])
    self.assertEqual(result["value"], -9)
    self.assertEqual(result["returns"], [9.0, -9.0, -9.0, 9.0])

  def test_karlchen_rule_can_be_switched_off(self):
    # Same tricks, but with the Karlchen rule disabled the last-trick
    # jack of clubs no longer scores: the -1 against Re disappears and
    # the game value rises by one.
    tricks = [scoring.Trick(0, [c(n) for n in names]) for names in _TRICKS]
    no_karlchen = scoring.Rules(karlchen=False)
    result = scoring.compute_result({1, 2}, tricks, no_karlchen)
    self.assertNotIn("karlchen", [label for label, _ in result["specials"]])
    self.assertEqual(result["value"], -8)


class GameParametersTest(absltest.TestCase):

  def test_rules_flow_from_game_parameters(self):
    default = pyspiel.load_game("python_doppelkopf")
    self.assertEqual(default.rules, scoring.Rules(True, True))
    tuned = pyspiel.load_game(
        "python_doppelkopf", {"second_dulle": False, "karlchen": False})
    self.assertEqual(tuned.rules, scoring.Rules(False, False))
    # The state a game hands out carries its rules to scoring/trick logic.
    self.assertEqual(tuned.new_initial_state().rules, tuned.rules)


if __name__ == "__main__":
  absltest.main()
