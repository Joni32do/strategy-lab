"""The learn lens: watch an algorithm find the strategy by itself.

For single-agent worlds (:class:`~strategy_lab.families.mdp.SinglePlayerGame`)
the lens runs a learning or planning algorithm on the game and shows what it
finds.

Grid worlds (FrozenLake, Cliff Walking)
    * ``value-iteration``: planning with the known model. Repeats the Bellman
      optimality backup until the values stop changing. No episodes needed.
    * ``q-learning``: learning from experience only. Each step moves
      ``Q(s, a)`` a fraction ``alpha`` toward ``r + gamma max_a' Q(s', a')``.
      The agent explores with an epsilon-greedy policy, breaking ties at random.

Bandits
    * ``epsilon-greedy``: pull the best average, but with probability epsilon
      a random arm.
    * ``ucb``: UCB1, the average plus a confidence bonus.
    * ``softmax``: pull arm ``i`` with probability proportional to
      ``exp(mean_i / temperature)``.

Bandits hide their odds, so the lens never reads those of a game in progress:
it learns on a *practice bandit* with the same number of arms and odds drawn
from ``seed``. After the last pull it uses the real arms and adds how your
own pulls compare.

Options: ``algorithm`` (``auto`` picks Q-learning on grids and UCB on bandits;
the result lists ``algorithms`` that apply to this game), ``episodes`` (grid
episodes, or bandit pulls), ``alpha``, ``gamma``, ``epsilon``,
``temperature``, ``seed``.

Result schema::

    {
      "kind": "gridworld" | "bandit",
      "algorithm": "q-learning", "algorithms": ["value-iteration", "q-learning"],
      "options": {"episodes", "alpha", "gamma", "epsilon", "temperature", "seed"},
      "curve":   {"kind": "return" | "bellman-error" | "reward",
                  "x": [...], "values": [...], "average": [...] | null, "window": int},
      "entropy": null | {"x": [...], "values": [bits], "max": <log2 #actions>},
      "overlay": {"actions": {"<action>": {"text", "tone", "value"}}},

      # gridworld only
      "rows", "cols", "tiles": ["S...", ".H.H", ...],   # map rows: S G H C # .
      "values":  {"<cell>": V},           # best Q of every cell
      "policy":  {"<cell>": "up"|"right"|"down"|"left"},   # greedy arrow, absent if unlearned
      "q":       {"<cell>": {"up": Q, ...}},
      "evaluation": {"episodes", "successRate", "meanReturn", "meanLength"},
      "sweeps":  null | <value-iteration sweeps>,

      # bandit only
      "practice": <bool>,                 # false once the real arms are known
      "arms":    ["A", "B", ...],
      "estimates": {"x": [...], "arms": [[estimate per step for arm 0], ...]},
      "regret":  {"x": [...], "values": [cumulative regret vs the best arm],
                  "baseline": <final regret of a random player>,
                  "best": null | <best arm>, "probs": null | [<true odds>]},
      "you":     null | {"regret": <your total regret>, "reward": <your total>}
    }

Curves are thinned to at most 300 points; ``x`` holds the 1-based episode or
step of each point.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

from strategy_lab.core import CHANCE
from strategy_lab.families.mdp import (
    DIRECTIONS, GridWorld, SinglePlayerGame, entropy_bits, greedy_actions, greedy_probs,
    epsilon_greedy_probs, softmax_probs,
)
from strategy_lab.games.bandit import LETTERS, Bandit, draw_probabilities, ucb1_index
from strategy_lab.lenses.base import Lens, overlay

GRID_ALGORITHMS = ["value-iteration", "q-learning"]
BANDIT_ALGORITHMS = ["epsilon-greedy", "ucb", "softmax"]
MAX_POINTS = 300
EVAL_EPISODES = 200


def thin(values: Sequence[float], limit: int = MAX_POINTS) -> tuple[list[int], list[float]]:
    """Keep at most ``limit`` evenly spaced points. Returns ``(1-based x, values)``."""
    n = len(values)
    stride = max(1, math.ceil(n / limit))
    idx = list(range(stride - 1, n, stride))
    if idx and idx[-1] != n - 1:
        idx.append(n - 1)
    return [i + 1 for i in idx], [round(float(values[i]), 4) for i in idx]


def moving_average(values: Sequence[float], window: int) -> list[float]:
    """Mean of the last ``window`` values (fewer at the start)."""
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= window:
            total -= values[i - window]
        out.append(total / min(i + 1, window))
    return out


def epsilon_greedy_entropy(ties: int, n: int, epsilon: float) -> float:
    """Entropy in bits of epsilon-greedy over ``n`` actions with ``ties`` best ones."""
    explore = epsilon / n
    best = explore + (1.0 - epsilon) / ties
    return entropy_bits([best] * ties + [explore] * (n - ties))


def curve_block(values: Sequence[float], kind: str, window: int = 20) -> dict:
    """A learning curve with its moving average, thinned for the page."""
    x, v = thin(values)
    _, avg = thin(moving_average(values, window))
    return {"kind": kind, "x": x, "values": v, "average": avg, "window": window}


class RLLens(Lens):
    id = "rl"
    title = "Learn"
    icon = "brain"
    blurb = "Let an algorithm find the strategy: plan with the model or learn by trying."
    concepts = ("mdp", "value-function", "bellman", "value-iteration", "q-learning",
                "exploration", "ucb", "policy-entropy", "regret", "discount")
    order = 40
    options = (
        {"name": "algorithm", "label": "Algorithm", "type": "choice", "default": "auto",
         "choices": ["auto"] + GRID_ALGORITHMS + BANDIT_ALGORITHMS},
        {"name": "episodes", "label": "Episodes (or pulls)", "type": "int", "default": 400,
         "min": 10, "max": 2000, "step": 50},
        {"name": "alpha", "label": "Learning rate alpha", "type": "float", "default": 0.2,
         "min": 0.01, "max": 1.0, "step": 0.01},
        {"name": "gamma", "label": "Discount gamma", "type": "float", "default": 0.99,
         "min": 0.0, "max": 1.0, "step": 0.01},
        {"name": "epsilon", "label": "Exploration epsilon", "type": "float", "default": 0.1,
         "min": 0.0, "max": 1.0, "step": 0.01},
        {"name": "temperature", "label": "Softmax temperature", "type": "float",
         "default": 0.1, "min": 0.01, "max": 5.0, "step": 0.01},
        {"name": "seed", "label": "Random seed", "type": "int", "default": 0, "min": 0,
         "max": 100000, "step": 1},
    )

    def options_for(self, game) -> tuple[dict, ...]:
        """Algorithms and sliders that fit ``game``: grids learn, bandits pull."""
        if isinstance(game, Bandit):
            algorithms, unused, label = BANDIT_ALGORITHMS, ("alpha", "gamma"), "Pulls"
        else:
            algorithms, unused, label = GRID_ALGORITHMS, ("temperature",), "Episodes"
        out = []
        for opt in self.options:
            opt = dict(opt)
            if opt["name"] == "algorithm":
                opt["choices"] = ["auto"] + algorithms
            elif opt["name"] == "episodes":
                opt["label"] = label
            elif opt["name"] in unused:
                opt["hidden"] = True
            out.append(opt)
        return tuple(out)

    def applies(self, game) -> bool:
        return isinstance(game, SinglePlayerGame) and (
            isinstance(game, GridWorld) or isinstance(game, Bandit))

    def run(self, session, options):
        g = session.game
        opts = {name: self.option(options, name) for name in
                ("episodes", "alpha", "gamma", "epsilon", "temperature", "seed")}
        algorithm = self.option(options, "algorithm")
        if isinstance(g, GridWorld):
            algorithm = algorithm if algorithm in GRID_ALGORITHMS else "q-learning"
            out = self._grid(session, algorithm, opts)
            out["algorithms"] = GRID_ALGORITHMS
        else:
            algorithm = algorithm if algorithm in BANDIT_ALGORITHMS else "ucb"
            out = self._bandit(session, algorithm, opts)
            out["algorithms"] = BANDIT_ALGORITHMS
        out["algorithm"], out["options"] = algorithm, opts
        return out

    # ----------------------------------------------------------- grid worlds
    def _grid(self, session, algorithm: str, o: dict) -> dict:
        g = session.game
        rng = random.Random(o["seed"])
        n = len(DIRECTIONS)
        if algorithm == "value-iteration":
            plan = g.optimal(o["gamma"])
            q = {c: dict(row) for c, row in plan.q.items()}
            curve = curve_block(plan.deltas, "bellman-error")
            curve["average"] = None
            entropy, sweeps = None, plan.sweeps
        else:
            q, returns, entropies = self._q_learning(g, o, rng)
            curve = curve_block(returns, "return")
            x, e = thin(entropies)
            entropy, sweeps = {"x": x, "values": e, "max": math.log2(n)}, None
        out = {
            "kind": "gridworld", "rows": g.rows, "cols": g.cols, "tiles": list(g.tiles),
            "curve": curve,
            "entropy": entropy, "sweeps": sweeps,
            "values": {str(c): round(max(row.values()), 4) for c, row in q.items()},
            "policy": self._policy(g, q),
            "q": {str(c): {d: round(v, 4) for d, v in row.items()} for c, row in q.items()},
            "evaluation": self._evaluate(g, q, rng),
            "overlay": {"actions": {}},
        }
        s = session.state
        if not session.terminal and g.current_player(s) != CHANCE and s.pos in q:
            out["overlay"] = overlay(q[s.pos])
        return out

    @staticmethod
    def _policy(g: GridWorld, q: dict) -> dict:
        arrows = {}
        for cell, row in q.items():
            if g.tile(cell) in "GHC":
                continue
            best = greedy_actions(row, tol=1e-9)
            if len(best) < len(row):
                arrows[str(cell)] = next(d for d in DIRECTIONS if d in best)
        return arrows

    @staticmethod
    def _sample(outcomes, rng: random.Random):
        r, acc = rng.random(), 0.0
        for p, nxt, reward, done in outcomes:
            acc += p
            if r < acc:
                return nxt, reward, done
        return outcomes[-1][1:]

    @staticmethod
    def _choose(row: list[float], epsilon: float, rng: random.Random) -> tuple[int, int]:
        """Epsilon-greedy over ``row`` with random ties. Returns ``(index, #ties)``."""
        best = max(row)
        ties = [i for i, v in enumerate(row) if v >= best - 1e-9]
        if rng.random() < epsilon:
            return rng.randrange(len(row)), len(ties)
        return rng.choice(ties), len(ties)

    def _q_learning(self, g: GridWorld, o: dict, rng: random.Random):
        """Tabular Q-learning. Returns ``(Q, return per episode, mean entropy per episode)``."""
        model = g.model
        n = len(DIRECTIONS)
        q = {c: {d: 0.0 for d in DIRECTIONS} for c in model}
        alpha, gamma, eps = o["alpha"], o["gamma"], o["epsilon"]
        entropy_of = {k: epsilon_greedy_entropy(k, n, eps) for k in range(1, n + 1)}
        returns, entropies = [], []
        for _ in range(o["episodes"]):
            cell, total, bits, steps = g.start, 0.0, 0.0, 0
            while steps < g.step_limit:
                row = [q[cell][d] for d in DIRECTIONS]
                i, ties = self._choose(row, eps, rng)
                bits += entropy_of[ties]
                move = DIRECTIONS[i]
                nxt, reward, done = self._sample(model[cell][move], rng)
                target = reward + (0.0 if done else gamma * max(q[nxt].values()))
                q[cell][move] += alpha * (target - q[cell][move])
                total += reward
                steps += 1
                cell = nxt
                if done:
                    break
            returns.append(total)
            entropies.append(bits / steps)
        return q, returns, entropies

    def _evaluate(self, g: GridWorld, q: dict, rng: random.Random) -> dict:
        """Play the greedy policy of ``q`` and count how often it reaches a goal."""
        model = g.model
        wins = total_return = total_len = 0
        for _ in range(EVAL_EPISODES):
            cell, steps, ret = g.start, 0, 0.0
            while steps < g.step_limit:
                row = [q[cell][d] for d in DIRECTIONS]
                i, _ = self._choose(row, 0.0, rng)
                nxt, reward, done = self._sample(model[cell][DIRECTIONS[i]], rng)
                ret += reward
                steps += 1
                cell = nxt
                if done:
                    wins += g.tile(cell) == "G"
                    break
            total_return += ret
            total_len += steps
        n = EVAL_EPISODES
        return {"episodes": n, "successRate": round(wins / n, 4),
                "meanReturn": round(total_return / n, 4), "meanLength": round(total_len / n, 2)}

    # --------------------------------------------------------------- bandits
    def _bandit(self, session, algorithm: str, o: dict) -> dict:
        g, s = session.game, session.state
        real = session.terminal and s.seed is not None
        probs = s.probs if real else draw_probabilities(o["seed"] * 7919 + 1, g.arms)
        rng = random.Random(o["seed"])
        run = self.run_bandit(probs, algorithm, o["episodes"], o["epsilon"],
                              o["temperature"], rng)
        best_p = max(probs)
        gap = best_p - sum(probs) / len(probs)
        steps = o["episodes"]
        xs, regret = thin(run["regret"])
        ex, _ = thin(run["rewards"])
        arms_traj = [thin(run["estimates"][i])[1] for i in range(g.arms)]
        ent_x, ent = thin(run["entropy"])
        you = None
        if real and s.trail:
            you = {"regret": round(sum(best_p - probs[a] for a, _ in s.trail), 4),
                   "reward": s.total}
        return {
            "kind": "bandit", "practice": not real,
            "curve": curve_block(run["rewards"], "reward"),
            "entropy": {"x": ent_x, "values": ent, "max": math.log2(g.arms)},
            "arms": [LETTERS[i] for i in range(g.arms)],
            "estimates": {"x": ex, "arms": arms_traj},
            "regret": {"x": xs, "values": regret, "baseline": round(gap * steps, 4),
                       "best": probs.index(best_p) if real else None,
                       "probs": list(probs) if real else None},
            "you": you, "overlay": {"actions": {}},
        }

    @staticmethod
    def run_bandit(probs: Sequence[float], algorithm: str, steps: int, epsilon: float,
                   temperature: float, rng: random.Random) -> dict:
        """Run ``steps`` pulls of a bandit algorithm on arms with odds ``probs``.

        Returns lists per step: ``rewards``, cumulative ``regret`` (expected,
        against the best arm), policy ``entropy`` in bits, and ``estimates``
        (mean estimate of each arm after each pull).
        """
        k = len(probs)
        best_p = max(probs)
        pulls, wins = [0] * k, [0] * k
        rewards, regret, entropy = [], [], []
        estimates = [[] for _ in range(k)]
        cumulative = 0.0
        for t in range(1, steps + 1):
            means = [w / n if n else 0.0 for w, n in zip(wins, pulls)]
            if algorithm == "ucb":
                dist = greedy_probs([ucb1_index(means[i], pulls[i], t) for i in range(k)])
            elif algorithm == "softmax":
                dist = softmax_probs(means, temperature)
            else:
                dist = epsilon_greedy_probs(means, epsilon)
            arm = rng.choices(range(k), weights=dist)[0]
            reward = 1 if rng.random() < probs[arm] else 0
            pulls[arm] += 1
            wins[arm] += reward
            cumulative += best_p - probs[arm]
            rewards.append(reward)
            regret.append(cumulative)
            entropy.append(entropy_bits(dist))
            for i in range(k):
                estimates[i].append(wins[i] / pulls[i] if pulls[i] else 0.0)
        return {"rewards": rewards, "regret": regret, "entropy": entropy,
                "estimates": estimates}
