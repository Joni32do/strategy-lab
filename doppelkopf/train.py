"""Expert-iteration training loop for the Doppelkopf master bot.

The expert is the PIMC search of `search.py`. Each iteration:

  1. Self-play: four copies of the expert play full deals; every
     decision (with a real choice) is recorded as (features, card the
     search picked, legality mask).
  2. Learning: the policy net is trained by cross-entropy to imitate
     the search decisions (replay buffer over recent iterations).
  3. Promotion: from the next iteration on, the expert's rollouts use
     the improved net instead of the rule-based bot, so the search
     itself gets stronger -- the expert-iteration flywheel.
  4. Evaluation: the bare net (greedy, no search) plays against three
     heuristic bots; the average return tracks progress. The best net
     so far is saved as `checkpoints/master.npz`, which `search.py`
     and the web UI pick up automatically.

Run from the open_spiel repository root:

    ../.venv/bin/python -m doppelkopf.train
    ../.venv/bin/python -m doppelkopf.train --iterations 8 --games 16
    ../.venv/bin/python -m doppelkopf.train --resume  # continue training

Everything is CPU-only numpy; a default run takes tens of minutes.
"""

import argparse
import json
import os
import random
import time

import numpy as np

from doppelkopf import cards
from doppelkopf import policy
from doppelkopf import worlds
from doppelkopf.bots import HeuristicBot
from doppelkopf.search import DEFAULT_CHECKPOINT, PIMCAdvisor


def deal(rng):
  """A fresh LightState with 12 random cards per seat."""
  deck = [c for c in range(cards.NUM_CARD_TYPES)] * 2
  rng.shuffle(deck)
  hands = [[0] * cards.NUM_CARD_TYPES for _ in range(cards.NUM_PLAYERS)]
  re_players = set()
  for i, card in enumerate(deck):
    seat = i // cards.CARDS_PER_PLAYER
    hands[seat][card] += 1
    if card == cards.CLUB_QUEEN:
      re_players.add(seat)
  return worlds.LightState(hands, 0, [], [], re_players)


def self_play_game(expert, rng, explore=0.1):
  """One self-played deal; returns (samples, returns).

  Every seat is played by the expert. Decisions with at least two legal
  cards are recorded as training samples (features, expert card, mask).
  With probability `explore` a random legal card is played instead of
  the expert's choice, so the buffer sees a wider slice of state space
  (the recorded target is still the expert's pick for that state).
  """
  state = deal(rng)
  samples = []
  while not state.is_terminal():
    player = state.current_player()
    legal = state.legal_actions()
    if len(legal) == 1:
      state.apply_action(legal[0])
      continue
    best = expert.evaluate(state, player)[0][0]
    samples.append((policy.encode(state, player), best,
                    policy.legal_mask(legal)))
    action = rng.choice(legal) if rng.random() < explore else best
    state.apply_action(action)
  return samples, state.returns()


def evaluate_net(net, num_games, rng):
  """Greedy net vs three heuristic bots; average return of the net seat.

  The net's seat rotates so deal luck evens out. Positive is better; a
  heuristic bot in the same setup scores 0 on average by symmetry.
  """
  total = 0.0
  for g in range(num_games):
    net_seat = g % cards.NUM_PLAYERS
    state = deal(rng)
    bots = {p: HeuristicBot(p, rng) for p in range(cards.NUM_PLAYERS)}
    while not state.is_terminal():
      player = state.current_player()
      legal = state.legal_actions()
      if player == net_seat and len(legal) > 1:
        state.apply_action(net.act(state, player, legal))
      else:
        state.apply_action(bots[player].step(state))
    total += state.returns()[net_seat]
  return total / num_games


def evaluate_pimc(advisor_factory, num_games, rng, deal_seed=None):
  """Full search bot vs three heuristic bots (slow; used sparingly).

  With `deal_seed` set, game g is dealt from Random(deal_seed + g), so
  two configurations can be compared on identical deals (paired
  evaluation, much lower variance).
  """
  total = 0.0
  for g in range(num_games):
    seat = g % cards.NUM_PLAYERS
    game_rng = random.Random(deal_seed + g) if deal_seed is not None else rng
    state = deal(game_rng)
    advisor = advisor_factory()
    bots = {p: HeuristicBot(p, game_rng) for p in range(cards.NUM_PLAYERS)}
    while not state.is_terminal():
      player = state.current_player()
      if player == seat:
        state.apply_action(advisor.evaluate(state, player)[0][0])
      else:
        state.apply_action(bots[player].step(state))
    total += state.returns()[seat]
  return total / num_games


class ReplayBuffer:
  """Keeps the most recent `capacity` (features, target, mask) samples."""

  def __init__(self, capacity=60000):
    self.capacity = capacity
    self.data = []

  def add(self, samples):
    self.data.extend(samples)
    if len(self.data) > self.capacity:
      self.data = self.data[-self.capacity:]

  def batches(self, batch_size, rng):
    order = list(range(len(self.data)))
    rng.shuffle(order)
    if not order:
      return
    starts = range(0, len(order) - batch_size + 1, batch_size) or [0]
    for start in starts:
      idx = order[start:start + batch_size]
      x = np.stack([self.data[i][0] for i in idx])
      y = np.array([self.data[i][1] for i in idx], np.int64)
      m = np.stack([self.data[i][2] for i in idx])
      yield x, y, m


def train(args):
  rng = random.Random(args.seed)
  out_dir = os.path.dirname(args.checkpoint) or "."
  os.makedirs(out_dir, exist_ok=True)
  metrics_path = os.path.join(out_dir, "metrics.jsonl")

  if args.resume and os.path.exists(args.checkpoint):
    net = policy.PolicyNet.load(args.checkpoint)
    best_eval = evaluate_net(net, args.eval_games, random.Random(args.seed))
    print(f"resumed from {args.checkpoint}, current eval {best_eval:+.2f}")
  else:
    net = policy.PolicyNet(seed=args.seed)
    best_eval = float("-inf")

  def pick_rollout_net():
    """Which policy the expert's rollouts use this iteration.

    A weak net makes PIMC *worse* than heuristic rollouts, so in 'auto'
    mode the net has to beat the heuristic bots head-on (positive eval
    by a margin) before the search trusts it.
    """
    if args.rollout == "heuristic":
      return None
    if args.rollout == "net":
      return net
    return net if best_eval >= args.promote_threshold else None

  buffer = ReplayBuffer(args.buffer)
  for iteration in range(args.iterations):
    t0 = time.time()
    rollout_net = pick_rollout_net()
    expert = PIMCAdvisor(num_worlds=args.worlds, net=rollout_net,
                         rng=random.Random(rng.random()))
    new_samples = 0
    for _ in range(args.games):
      samples, _ = self_play_game(expert, rng, args.explore)
      buffer.add(samples)
      new_samples += len(samples)
    selfplay_s = time.time() - t0

    t0 = time.time()
    losses = []
    for _ in range(args.epochs):
      for x, y, m in buffer.batches(args.batch_size, rng):
        losses.append(net.train_step(x, y, m, lr=args.lr))
    loss = float(np.mean(losses)) if losses else float("nan")
    train_s = time.time() - t0

    t0 = time.time()
    eval_return = evaluate_net(net, args.eval_games,
                               random.Random(args.seed + iteration))
    eval_s = time.time() - t0

    tag = ""
    if eval_return > best_eval:
      best_eval = eval_return
      net.save(args.checkpoint)
      tag = " -> saved master"
    net.save(os.path.join(out_dir, "latest.npz"))

    record = {
        "iteration": iteration,
        "rollout": "net" if rollout_net is not None else "heuristic",
        "samples": new_samples,
        "buffer": len(buffer.data),
        "loss": round(loss, 4),
        "eval_return": round(eval_return, 3),
        "best_eval": round(best_eval, 3),
        "selfplay_s": round(selfplay_s, 1),
        "train_s": round(train_s, 1),
        "eval_s": round(eval_s, 1),
    }
    with open(metrics_path, "a") as f:
      f.write(json.dumps(record) + "\n")
    print(f"iter {iteration:2d}  samples {new_samples:4d}  "
          f"loss {loss:.3f}  eval {eval_return:+.2f}  "
          f"(best {best_eval:+.2f}){tag}  "
          f"[play {selfplay_s:.0f}s train {train_s:.0f}s eval {eval_s:.0f}s]")

  if args.pimc_eval:
    # Which rollout policy makes the stronger search bot? Measure both
    # and record the winner so `search.best_advisor` (and the web UI)
    # uses the best configuration.
    final_net = policy.PolicyNet.load(args.checkpoint)
    deal_seed = args.seed * 100003  # Paired deals for both variants.
    score_net = evaluate_pimc(
        lambda: PIMCAdvisor(num_worlds=args.worlds, net=final_net,
                            rng=random.Random(rng.random())),
        args.pimc_eval, rng, deal_seed=deal_seed)
    score_heur = evaluate_pimc(
        lambda: PIMCAdvisor(num_worlds=args.worlds,
                            rng=random.Random(rng.random())),
        args.pimc_eval, rng, deal_seed=deal_seed)
    use_net = score_net >= score_heur
    print(f"PIMC vs 3x heuristic over {args.pimc_eval} games each: "
          f"net rollouts {score_net:+.2f}, heuristic rollouts "
          f"{score_heur:+.2f} -> master uses "
          f"{'net' if use_net else 'heuristic'} rollouts")
    meta = {
        "pimc_eval_net": round(score_net, 3),
        "pimc_eval_heuristic": round(score_heur, 3),
        "games": args.pimc_eval,
        "net_eval": round(best_eval, 3),
        "rollout": "net" if use_net else "heuristic",
    }
    with open(os.path.splitext(args.checkpoint)[0] + ".json", "w") as f:
      json.dump(meta, f, indent=2)
    with open(metrics_path, "a") as f:
      f.write(json.dumps(meta) + "\n")


def main():
  parser = argparse.ArgumentParser(
      description="Expert-iteration training for the Doppelkopf master bot.")
  parser.add_argument("--iterations", type=int, default=8)
  parser.add_argument("--games", type=int, default=12,
                      help="self-play deals per iteration")
  parser.add_argument("--worlds", type=int, default=12,
                      help="PIMC determinizations per decision")
  parser.add_argument("--epochs", type=int, default=3,
                      help="training passes over the buffer per iteration")
  parser.add_argument("--batch-size", type=int, default=256)
  parser.add_argument("--lr", type=float, default=1e-3)
  parser.add_argument("--buffer", type=int, default=60000)
  parser.add_argument("--explore", type=float, default=0.1)
  parser.add_argument("--eval-games", type=int, default=80,
                      help="bare-net evaluation deals per iteration")
  parser.add_argument("--pimc-eval", type=int, default=0,
                      help="final search-bot evaluation deals (slow)")
  parser.add_argument("--rollout", choices=("auto", "heuristic", "net"),
                      default="auto",
                      help="expert rollout policy; 'auto' promotes the net "
                           "once it beats the heuristic bots head-on")
  parser.add_argument("--promote-threshold", type=float, default=0.3,
                      help="bare-net eval needed before 'auto' switches "
                           "the expert's rollouts to the net")
  parser.add_argument("--seed", type=int, default=1)
  parser.add_argument("--resume", action="store_true")
  parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
  args = parser.parse_args()
  train(args)


if __name__ == "__main__":
  main()
