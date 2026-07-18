"""Perfect-information Monte Carlo (PIMC) search for Doppelkopf.

For each legal card the advisor samples worlds consistent with the
player's view (see `worlds.py`), plays the card in every world, rolls
the game out to the end with a rollout policy for all four seats, and
averages the player's return. The same worlds are reused for every
candidate card (common random numbers) to cut variance.

The rollout policy is either the fast rule-based `HeuristicBot` or a
trained `PolicyNet` (see `train.py`); with a trained net this is the
"master bot" that the web UI's advice panel consults.
"""

import os
import random

from doppelkopf import cards
from doppelkopf import worlds
from doppelkopf.bots import HeuristicBot
from doppelkopf.game import legal_cards

DEFAULT_CHECKPOINT = os.path.join(
    os.path.dirname(__file__), "checkpoints", "master.npz")


class HeuristicRollout:
  """Finishes a determinized world with four rule-based bots."""

  def __init__(self, rng):
    self.bots = [HeuristicBot(p, rng) for p in range(cards.NUM_PLAYERS)]

  def finish(self, world):
    while not world.is_terminal():
      world.apply_action(self.bots[world.current_player()].step(world))
    return world.returns()


class NetRollout:
  """Finishes a determinized world with a trained policy network.

  A small temperature keeps rollouts from being deterministic copies of
  each other; epsilon mixes in the heuristic bot as a safety net so a
  half-trained net cannot derail the search completely.
  """

  def __init__(self, net, rng, temperature=0.3, epsilon=0.1):
    self.net = net
    self.rng = rng
    self.temperature = temperature
    self.epsilon = epsilon
    self.heuristic = HeuristicRollout(rng)

  def finish(self, world):
    while not world.is_terminal():
      player = world.current_player()
      legal = world.legal_actions()
      if len(legal) == 1:
        world.apply_action(legal[0])
      elif self.rng.random() < self.epsilon:
        world.apply_action(self.heuristic.bots[player].step(world))
      else:
        world.apply_action(self.net.act(world, player, legal, self.rng,
                                        self.temperature))
    return world.returns()


class PIMCAdvisor:
  """Ranks the legal cards of the player to act by expected return."""

  def __init__(self, num_worlds=20, net=None, rng=None,
               rollout_temperature=0.3, heuristic_share=0.1):
    self.num_worlds = num_worlds
    self.rng = rng or random.Random()
    if net is None:
      self.rollout = HeuristicRollout(self.rng)
    else:
      self.rollout = NetRollout(net, self.rng, rollout_temperature,
                                heuristic_share)

  def evaluate(self, state, player=None):
    """Scores every legal card for the player to act.

    Args:
      state: a DoppelkopfState or LightState in the play phase.
      player: acting seat; defaults to state.current_player().

    Returns:
      List of (card, expected_return) sorted best first. The expected
      return is in game points from `player`'s perspective.
    """
    if player is None:
      player = state.current_player()
    legal = legal_cards(state.hands[player], state.current_trick)
    if len(legal) == 1:
      return [(legal[0], 0.0)]

    sampled = [worlds.sample_world(state, player, self.rng)
               for _ in range(self.num_worlds)]
    scores = []
    for card in legal:
      total = 0.0
      for world in sampled:
        w = world.clone()
        w.apply_action(card)
        total += self.rollout.finish(w)[player]
      scores.append((card, total / len(sampled)))
    scores.sort(key=lambda cs: -cs[1])
    return scores


class MasterBot:
  """Plays the top move of a PIMC advisor; drop-in for HeuristicBot."""

  def __init__(self, player, advisor=None, rng=None):
    self.player = player
    self.advisor = advisor or PIMCAdvisor(rng=rng)

  def step(self, state):
    return self.advisor.evaluate(state, self.player)[0][0]


def load_net(checkpoint=DEFAULT_CHECKPOINT):
  """The trained policy net, or None if no checkpoint exists yet."""
  if not os.path.exists(checkpoint):
    return None
  from doppelkopf.policy import PolicyNet
  return PolicyNet.load(checkpoint)


def resolve_net(checkpoint=DEFAULT_CHECKPOINT):
  """The net the search should roll out with, or None for heuristic.

  Training writes a sidecar json recording whether net rollouts or
  heuristic rollouts made the stronger search bot; honour it if present.
  """
  net = load_net(checkpoint)
  if net is None:
    return None
  meta_path = os.path.splitext(checkpoint)[0] + ".json"
  if os.path.exists(meta_path):
    import json
    with open(meta_path) as f:
      if json.load(f).get("rollout") == "heuristic":
        return None
  return net


def best_advisor(num_worlds=20, rng=None, checkpoint=DEFAULT_CHECKPOINT):
  """Strongest advisor available given the training results so far."""
  return PIMCAdvisor(num_worlds=num_worlds, net=resolve_net(checkpoint),
                     rng=rng)
