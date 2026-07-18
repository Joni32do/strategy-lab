"""Tests for the AI stack: worlds, policy net, PIMC search, training."""

import argparse
import os
import random

from absl.testing import absltest
import numpy as np

import pyspiel

import doppelkopf.game  # noqa: F401  (registers python_doppelkopf)
from doppelkopf import cards
from doppelkopf import policy
from doppelkopf import scoring
from doppelkopf import search
from doppelkopf import train
from doppelkopf import worlds
from doppelkopf.bots import HeuristicBot


def c(name):
  rank, suit = name[:-1], name[-1]
  return cards.make_card(
      cards.SUIT_LETTERS.index(suit), cards.RANK_LETTERS.index(rank))


def played_out_state(seed, num_moves):
  """A LightState advanced `num_moves` plays into a random deal."""
  rng = random.Random(seed)
  state = train.deal(rng)
  bots = [HeuristicBot(p, rng) for p in range(cards.NUM_PLAYERS)]
  for _ in range(num_moves):
    state.apply_action(bots[state.current_player()].step(state))
  return state


class LightStateTest(absltest.TestCase):

  def test_matches_openspiel_state(self):
    """LightState replicates the pyspiel game move for move."""
    game = pyspiel.load_game("python_doppelkopf")
    rng = random.Random(11)
    for _ in range(3):
      ref = game.new_initial_state()
      while ref.is_chance_node():
        actions, probs = zip(*ref.chance_outcomes())
        ref.apply_action(rng.choices(actions, probs)[0])
      light = worlds.LightState(ref.hands, ref.trick_leader,
                                ref.current_trick, ref.tricks,
                                ref.re_players)
      while not ref.is_terminal():
        player = ref.current_player()
        self.assertEqual(light.current_player(), player)
        self.assertCountEqual(light.legal_actions(),
                              ref.legal_actions(player))
        action = rng.choice(ref.legal_actions(player))
        ref.apply_action(action)
        light.apply_action(action)
      self.assertTrue(light.is_terminal())
      self.assertEqual(light.returns(), ref.returns())


class WorldsTest(absltest.TestCase):

  def test_infer_voids(self):
    trick = scoring.Trick(0, [c("AS"), c("9H"), c("KS"), c("9D")])
    state = worlds.LightState(
        [[0] * 24] * 4, trick.winner, [], [trick], set())
    voids = worlds.infer_voids(state)
    self.assertEqual(voids[0], set())              # Led, no info.
    self.assertEqual(voids[1], {cards.SPADES})     # Threw a heart.
    self.assertEqual(voids[2], set())              # Followed suit.
    self.assertEqual(voids[3], {cards.SPADES})     # Trumped in.

  def test_sampled_worlds_are_consistent(self):
    state = played_out_state(seed=5, num_moves=18)
    player = state.current_player()
    voids = worlds.infer_voids(state)
    played_by_seat = worlds.cards_played_by_seat(state)
    played = worlds.played_counts(state)
    rng = random.Random(2)

    for _ in range(50):
      world = worlds.sample_world(state, player, rng)
      # Public state and the observer's hand are untouched.
      self.assertEqual(world.hands[player], state.hands[player])
      self.assertEqual(world.tricks, state.tricks)
      self.assertEqual(world.current_trick, state.current_trick)
      self.assertEqual(world.trick_leader, state.trick_leader)
      # Hand sizes match the number of cards everyone still holds.
      for seat in range(cards.NUM_PLAYERS):
        self.assertEqual(sum(world.hands[seat]),
                         cards.CARDS_PER_PLAYER - played_by_seat[seat])
      # Exactly two copies of every card type across hands + discard.
      for card in range(cards.NUM_CARD_TYPES):
        held = sum(world.hands[seat][card]
                   for seat in range(cards.NUM_PLAYERS))
        self.assertEqual(held + played[card], 2,
                         msg=cards.card_str(card))
      # Known voids are respected.
      for seat in range(cards.NUM_PLAYERS):
        for card in range(cards.NUM_CARD_TYPES):
          if world.hands[seat][card]:
            self.assertNotIn(cards.card_class(card), voids[seat])
      # Team assignment matches where the club queens ended up.
      queens = worlds._re_players_of(world)
      self.assertEqual(world.re_players, queens)
      self.assertContainsSubset(state.known_re_players(),
                                world.re_players)

  def test_own_re_membership_is_preserved(self):
    # The observer holds a club queen; every sampled world must agree.
    state = played_out_state(seed=9, num_moves=6)
    holders = [p for p in range(cards.NUM_PLAYERS)
               if state.hands[p][cards.CLUB_QUEEN] > 0]
    if not holders:  # pragma: no cover (seed chosen so this holds)
      self.skipTest("no queen still in hand for this seed")
    player = holders[0]
    rng = random.Random(3)
    for _ in range(20):
      world = worlds.sample_world(state, player, rng)
      self.assertIn(player, world.re_players)


class PolicyTest(absltest.TestCase):

  def test_features_only_depend_on_the_players_view(self):
    state = played_out_state(seed=4, num_moves=15)
    player = state.current_player()
    rng = random.Random(0)
    base = policy.encode(state, player)
    self.assertEqual(base.shape, (policy.NUM_FEATURES,))
    for _ in range(5):
      world = worlds.sample_world(state, player, rng)
      np.testing.assert_array_equal(policy.encode(world, player), base)

  def test_probs_are_masked_and_normalized(self):
    state = played_out_state(seed=4, num_moves=15)
    player = state.current_player()
    legal = state.legal_actions()
    net = policy.PolicyNet(seed=2)
    p = net.probs(policy.encode(state, player), policy.legal_mask(legal))
    self.assertAlmostEqual(float(p.sum()), 1.0, places=5)
    self.assertEqual(float(p[~policy.legal_mask(legal)].sum()), 0.0)
    self.assertTrue(np.all(p[policy.legal_mask(legal)] > 0))

  def test_training_reduces_loss(self):
    rng = np.random.default_rng(0)
    n = 128
    x = rng.normal(size=(n, policy.NUM_FEATURES)).astype(np.float32)
    masks = np.zeros((n, cards.NUM_CARD_TYPES), bool)
    targets = np.zeros(n, np.int64)
    for i in range(n):
      legal = rng.choice(cards.NUM_CARD_TYPES, size=5, replace=False)
      masks[i, legal] = True
      targets[i] = legal[0]
    net = policy.PolicyNet(seed=3)
    first = net.train_step(x, targets, masks)
    for _ in range(150):
      last = net.train_step(x, targets, masks)
    self.assertLess(last, first * 0.5)

  def test_save_load_roundtrip(self):
    net = policy.PolicyNet(seed=4)
    x = np.random.default_rng(1).normal(
        size=policy.NUM_FEATURES).astype(np.float32)
    path = os.path.join(self.create_tempdir().full_path, "net.npz")
    net.save(path)
    clone = policy.PolicyNet.load(path)
    np.testing.assert_allclose(clone.logits(x), net.logits(x), rtol=1e-6)


class SearchTest(absltest.TestCase):

  def test_scores_cover_legal_actions_sorted(self):
    state = played_out_state(seed=6, num_moves=13)
    advisor = search.PIMCAdvisor(num_worlds=4, rng=random.Random(1))
    scores = advisor.evaluate(state)
    self.assertCountEqual([card for card, _ in scores],
                          state.legal_actions())
    values = [score for _, score in scores]
    self.assertEqual(values, sorted(values, reverse=True))

  def test_ruffs_the_fat_trick(self):
    # 25 points on the table, seat 0 is void in spades and holds exactly
    # one trump: taking the trick must come out clearly on top.
    hand0 = [0] * cards.NUM_CARD_TYPES
    for name in ("9D", "9H", "9H", "KH", "KH", "AH", "AH",
                 "9C", "9C", "KC", "KC", "10C"):
      hand0[c(name)] += 1
    state = worlds.LightState(
        [hand0, [0] * 24, [0] * 24, [0] * 24],
        trick_leader=1,
        current_trick=[c("AS"), c("10S"), c("KS")],
        tricks=[], re_players={1, 3})
    self.assertEqual(state.current_player(), 0)
    advisor = search.PIMCAdvisor(num_worlds=24, rng=random.Random(5))
    scores = advisor.evaluate(state, 0)
    self.assertEqual(scores[0][0], c("9D"))

  def test_single_legal_action_shortcut(self):
    hand1 = [0] * cards.NUM_CARD_TYPES
    hand1[c("AS")] = 1
    state = worlds.LightState(
        [[0] * 24, hand1, [0] * 24, [0] * 24],
        trick_leader=0, current_trick=[c("KS")], tricks=[],
        re_players=set())
    advisor = search.PIMCAdvisor(num_worlds=4, rng=random.Random(1))
    self.assertEqual(advisor.evaluate(state, 1), [(c("AS"), 0.0)])

  def test_master_bot_plays_the_top_move(self):
    state = played_out_state(seed=6, num_moves=13)
    player = state.current_player()
    top = search.PIMCAdvisor(
        num_worlds=6, rng=random.Random(2)).evaluate(state, player)[0][0]
    bot = search.MasterBot(
        player, search.PIMCAdvisor(num_worlds=6, rng=random.Random(2)))
    self.assertEqual(bot.step(state), top)

  def test_net_rollout_advisor_runs(self):
    state = played_out_state(seed=6, num_moves=13)
    net = policy.PolicyNet(seed=5)
    advisor = search.PIMCAdvisor(num_worlds=3, net=net,
                                 rng=random.Random(4))
    scores = advisor.evaluate(state)
    self.assertCountEqual([card for card, _ in scores],
                          state.legal_actions())


class TrainTest(absltest.TestCase):

  def test_deal_is_a_legal_doppelkopf_deal(self):
    state = train.deal(random.Random(0))
    self.assertEqual([sum(h) for h in state.hands], [12, 12, 12, 12])
    for card in range(cards.NUM_CARD_TYPES):
      self.assertEqual(sum(h[card] for h in state.hands), 2)
    self.assertEqual(state.re_players,
                     {p for p in range(cards.NUM_PLAYERS)
                      if state.hands[p][cards.CLUB_QUEEN] > 0})

  def test_tiny_training_run_writes_checkpoints(self):
    out = self.create_tempdir().full_path
    ckpt = os.path.join(out, "master.npz")
    args = argparse.Namespace(
        iterations=1, games=1, worlds=3, epochs=1, batch_size=32,
        lr=1e-3, buffer=1000, explore=0.1, eval_games=2, pimc_eval=0,
        rollout="auto", promote_threshold=0.3, seed=0, resume=False,
        checkpoint=ckpt)
    train.train(args)
    self.assertTrue(os.path.exists(ckpt))
    self.assertTrue(os.path.exists(os.path.join(out, "latest.npz")))
    self.assertTrue(os.path.exists(os.path.join(out, "metrics.jsonl")))
    net = policy.PolicyNet.load(ckpt)
    state = played_out_state(seed=1, num_moves=4)
    player = state.current_player()
    self.assertIn(net.act(state, player, state.legal_actions()),
                  state.legal_actions())


if __name__ == "__main__":
  absltest.main()
