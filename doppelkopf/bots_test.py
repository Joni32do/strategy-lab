"""Tests for the rule-based HeuristicBot."""

import random

from absl.testing import absltest

from doppelkopf import cards
from doppelkopf import scoring
from doppelkopf import worlds
from doppelkopf.bots import HeuristicBot
from doppelkopf.train import deal


def c(name):
  rank, suit = name[:-1], name[-1]
  return cards.make_card(
      cards.SUIT_LETTERS.index(suit), cards.RANK_LETTERS.index(rank))


def hand_counts(names):
  hand = [0] * cards.NUM_CARD_TYPES
  for name in names:
    hand[c(name)] += 1
  return hand


class HeuristicBotTest(absltest.TestCase):

  def test_plays_legal_through_full_games(self):
    rng = random.Random(3)
    for _ in range(20):
      state = deal(rng)
      bots = [HeuristicBot(p, rng) for p in range(cards.NUM_PLAYERS)]
      while not state.is_terminal():
        player = state.current_player()
        card = bots[player].step(state)
        self.assertIn(card, state.legal_actions())
        state.apply_action(card)
      self.assertLen(state.tricks, cards.NUM_TRICKS)
      self.assertEqual(sum(t.points for t in state.tricks),
                       cards.TOTAL_POINTS)

  def test_leads_a_plain_ace(self):
    hand = hand_counts(["AC", "AC", "9C", "9C", "KH", "KH", "9H", "9H",
                        "KS", "KS", "9S", "9S"])
    state = worlds.LightState(
        [hand, [0] * 24, [0] * 24, [0] * 24], 0, [], [], set())
    bot = HeuristicBot(0, random.Random(1))
    card = bot.step(state)
    self.assertEqual(cards.rank_of(card), cards.ACE)
    self.assertFalse(cards.is_trump(card))

  def test_feeds_points_to_partner_with_solid_card(self):
    # Trick 1: seat 1 trumped seat 0's heart lead with a club queen, so
    # seat 1 is publicly Re. Seat 2 also holds a club queen: partners.
    trick1 = scoring.Trick(0, [c("9H"), c("QC"), c("9H"), c("9S")])
    self.assertEqual(trick1.winner, 1)
    # Trick 2: partner seat 1 leads a solid ace of spades; seat 2 holds
    # no spades and should throw it the fattest card (the ace of hearts).
    hand2 = hand_counts(["QC", "AH", "9D", "9C", "9C", "KC", "KC",
                         "10C", "10C", "KH", "KH"])
    state = worlds.LightState(
        [[0] * 24, [0] * 24, hand2, [0] * 24],
        trick_leader=1, current_trick=[c("AS")], tricks=[trick1],
        re_players={1, 2})
    bot = HeuristicBot(2, random.Random(1))
    self.assertEqual(state.current_player(), 2)
    self.assertEqual(bot.step(state), c("AH"))

  def test_ruffs_fat_opponent_trick_cheaply(self):
    # Seat 3 (not Re, no known partners) sees 21 points led by opponents
    # and holds one small trump: it should take the trick with it.
    hand3 = hand_counts(["9D", "9H", "9H", "KH", "KH", "9C", "9C",
                         "KC", "KC", "10C", "10C", "AC"])
    state = worlds.LightState(
        [[0] * 24, [0] * 24, [0] * 24, hand3],
        trick_leader=1, current_trick=[c("AS"), c("10S")], tricks=[],
        re_players={0, 1})
    bot = HeuristicBot(3, random.Random(1))
    self.assertEqual(state.current_player(), 3)
    self.assertEqual(bot.step(state), c("9D"))

  def test_discards_cheap_when_it_cannot_win(self):
    # Opponents lead a dulle (unbeatable); with only plain cards in
    # hand, the bot should not waste points on the lost trick.
    hand2 = hand_counts(["9C", "9C", "KC", "KC", "AH", "AH",
                         "9S", "9S", "KS", "KS", "10S", "10S"])
    state = worlds.LightState(
        [[0] * 24, [0] * 24, hand2, [0] * 24],
        trick_leader=1, current_trick=[c("10H")], tricks=[],
        re_players={0, 1})
    bot = HeuristicBot(2, random.Random(1))
    card = bot.step(state)
    self.assertEqual(cards.card_points(card), 0)


if __name__ == "__main__":
  absltest.main()
