"""The multi-armed bandit: learn which slot machine pays best while you play.

Several arms, each a slot machine that pays 1 with a hidden probability ``p``
and 0 otherwise (Bernoulli arms). You get a fixed number of pulls. Every pull
is both a payout *and* a lesson: pulling the best-looking arm earns now,
pulling an unknown arm may earn more later. This is the smallest setting of
the exploration-exploitation trade-off (Sutton and Barto, chapter 2).

Design notes
------------
* The hidden probabilities are drawn through a **seed-as-outcome chance
  node**: the first move of every game is a chance node whose outcome is a
  random seed, and the probabilities are derived from it. The log therefore
  replays exactly. The seed step is private in the move log, so the
  probabilities do not leak into what the page shows.
* Each pull resolves its reward through an explicit chance node with the
  outcomes ``(0, 1 - p)`` and ``(1, p)``.
* The bots and cards see only what a player sees: pull counts and wins per
  arm, never the hidden probabilities.
* A bandit is an MDP with one state. The honest state for a learner is the
  belief about the arms, i.e. the counts (see ``models``).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.mdp import SinglePlayerGame

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def draw_probabilities(seed: int, arms: int) -> tuple[float, ...]:
    """The hidden success probabilities of ``arms`` arms, derived from ``seed``."""
    rng = random.Random(seed)
    return tuple(round(rng.uniform(0.05, 0.95), 2) for _ in range(arms))


def ucb1_index(mean: float, pulls: int, t: int) -> float:
    """The UCB1 score of an arm: its mean plus a confidence bonus (Auer et al., 2002).

    ``bonus = sqrt(2 ln t / pulls)`` shrinks as an arm is pulled more, so a
    rarely pulled arm keeps getting a chance. An unpulled arm scores infinity.
    """
    if pulls == 0:
        return math.inf
    return mean + math.sqrt(2.0 * math.log(max(t, 1)) / pulls)


@dataclass
class BanditState:
    """What happened so far. ``probs`` is hidden from the player and the bots.

    Attributes:
        seed: the chance outcome that fixes the arms; ``None`` before it is drawn.
        probs: the hidden success probability of each arm.
        pulls: how often each arm was pulled.
        wins: how often each arm paid.
        pending: the arm just pulled while its reward chance node is open.
        total: reward collected so far.
        n: pulls resolved so far.
        trail: ``(arm, reward)`` for each resolved pull, in order.
    """

    pulls: list[int]
    wins: list[int]
    seed: int | None = None
    probs: tuple[float, ...] = ()
    pending: int | None = None
    total: float = 0.0
    n: int = 0
    trail: list[tuple[int, int]] = field(default_factory=list)


class Bandit(SinglePlayerGame):
    id = "bandit"
    name = "Multi-armed bandit"
    icon = "slot"
    tagline = "Which machine pays best? Every pull earns and teaches."
    chapter = "learning"
    order = 10
    concepts = ("mdp", "reward-return", "exploration", "ucb", "regret", "policy-entropy")

    params = {
        "arms": Param(5, "Arms", "How many slot machines there are.", min=2, max=10),
        "pulls": Param(30, "Pulls", "How many times you may pull in total.", min=5, max=500),
    }
    stochastic = True
    perfect_information = False

    rulebook = Rulebook(
        summary="Several slot machines pay 1 or 0 with hidden odds. You have a fixed "
                "number of pulls. Collect as much as you can.",
        steps=(
            ("The arms", "Each arm pays 1 with its own hidden probability, otherwise 0. "
                         "The odds never change during the game."),
            ("A pull", "Pick an arm. It pays 1 or 0, and the page updates that arm's "
                       "record: pulls and average payout so far."),
            ("The end", "After the last pull the true odds are revealed. Your return is "
                        "the total you collected. Beating half the pulls beats a coin flip."),
        ),
        extra=(
            ("Bernoulli arms", "Every payout is an independent 0 or 1 draw, so an arm "
                               "that pays 70% still gives 0 three times in ten."),
            ("Hidden odds", "The odds are drawn at the start through a chance step that "
                            "the move log hides from you."),
        ),
        source="http://incompleteideas.net/book/RLbook2020.pdf",
    )

    models = (
        Model("single", "One state, true odds known", True,
              state="a single state: there is nothing to remember",
              size="1 state",
              actions="pull arm 1 .. k",
              transition="each pull pays 1 with the arm's true probability",
              reward="1 for a payout, 0 otherwise; gamma = 1",
              note="Trivial to solve: pull the best arm every time. It is not the game "
                   "you play, because the true odds are hidden."),
        Model("means", "Average payout per arm", False,
              state="the observed average payout of each arm",
              size="k numbers between 0 and 1",
              actions="pull arm 1 .. k",
              transition="the averages move after each pull, by an amount that depends on "
                         "how many pulls they rest on",
              reward="1 for a payout, 0 otherwise",
              note="Not Markov. An arm with mean 1.0 after one pull and one with mean 0.7 "
                   "after 100 pulls look different, but the averages hide how sure they "
                   "are, and certainty decides what to explore."),
        Model("counts", "Pulls and wins per arm (belief state)", True,
              state="how many times each arm was pulled and how many times it paid",
              size="about (pulls + 1)^(2k) in the worst case",
              actions="pull arm 1 .. k",
              transition="one count goes up by 1 after each pull; the payout chance is the "
                         "posterior mean",
              reward="1 for a payout, 0 otherwise",
              note="The counts are a sufficient statistic for the hidden odds, so this "
                   "state is Markov. It is the belief-state MDP that Bayesian bandit "
                   "methods solve."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Pulls a random arm every time.", 1, icon="dice"),
        Bot("greta", "Greedy Greta", "Always pulls the arm with the best average so far. "
            "Locks on early.", 2, cards=("exploit",), icon="money"),
        Bot("cleo", "Curious Cleo", "Pulls the best arm, but 1 time in 10 tries a random "
            "one.", 3, cards=("explore", "exploit"), icon="compass"),
        Bot("ursula", "Upper-bound Ursula", "Plays UCB1: the best average plus a bonus for "
            "arms she knows little about.", 4, cards=("ucb",), icon="chart"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("coin", "Beat a coin flip: collect more than half your pulls", "win", 1),
        Challenge("rl", "Open the Learn lens", "lens", 1, lens="rl"),
        Challenge("twenty", "Collect 20 payouts in 30 pulls", "score", 2, value=20),
    )

    # ------------------------------------------------------------------ rules
    @property
    def arms(self) -> int:
        return self.p["arms"]

    def initial_state(self) -> BanditState:
        return BanditState(pulls=[0] * self.arms, wins=[0] * self.arms)

    def copy_state(self, s: BanditState) -> BanditState:
        return BanditState(s.pulls[:], s.wins[:], s.seed, s.probs, s.pending, s.total, s.n,
                           s.trail[:])

    def current_player(self, s: BanditState) -> int:
        return CHANCE if s.seed is None or s.pending is not None else 0

    def legal_actions(self, s: BanditState) -> list[Action]:
        return list(range(self.arms))

    def chance_outcomes(self, s: BanditState) -> list[tuple[Action, float]]:
        if s.seed is None:
            raise NotImplementedError("the arms are drawn from a seed, not enumerated")
        p = s.probs[s.pending]
        return [(0, 1.0 - p), (1, p)]

    def sample_chance(self, s: BanditState, rng) -> Action:
        if s.seed is None:
            return rng.randrange(2 ** 31)
        return super().sample_chance(s, rng)

    def move(self, s: BanditState, a: Action) -> None:
        if s.seed is None:
            s.seed = int(a)
            s.probs = draw_probabilities(s.seed, self.arms)
        elif s.pending is None:
            s.pending = int(a)
        else:
            arm, reward = s.pending, int(a)
            s.pulls[arm] += 1
            s.wins[arm] += reward
            s.total += reward
            s.n += 1
            s.trail.append((arm, reward))
            s.pending = None

    def is_terminal(self, s: BanditState) -> bool:
        return s.n >= self.p["pulls"]

    def outcome(self, returns: list[float], player: int) -> str:
        half = self.p["pulls"] / 2.0
        if returns[0] > half:
            return "win"
        return "draw" if returns[0] == half else "loss"

    # ---------------------------------------------------------- what you see
    @staticmethod
    def means(s: BanditState) -> list[float]:
        """Observed average payout per arm (0 for an arm never pulled)."""
        return [w / n if n else 0.0 for w, n in zip(s.wins, s.pulls)]

    def observation(self, s: BanditState, player: int) -> str:
        record = ", ".join(f"{LETTERS[i]}: {w}/{n}" for i, (w, n) in
                           enumerate(zip(s.wins, s.pulls)))
        return f"wins/pulls per arm: {record}"

    def privacy(self, s: BanditState, a: Action, player: int) -> tuple[int, ...] | None:
        """The seed step fixes the hidden odds, so nobody may read it from the log."""
        return () if player == CHANCE and s.seed is None else None

    def describe_hidden(self, s: BanditState, a: Action, player: int) -> str:
        return "draws the hidden odds"

    # ------------------------------------------------------------- rule cards
    def _best(self, values: list[float], candidates: list[Action], rng):
        top = max(values[a] for a in candidates)
        return rng.choice([a for a in candidates if values[a] >= top - 1e-9])

    @pick("untried", "Try untried arms",
          "Pull an arm you have never pulled before you trust any average.", "sparkle")
    def card_untried(self, s, candidates, player, rng):
        fresh = [a for a in candidates if s.pulls[a] == 0]
        return fresh[0] if fresh else None

    @pick("exploit", "Exploit the best mean",
          "Pull the arm with the highest average payout so far.", "trophy")
    def card_exploit(self, s, candidates, player, rng):
        return self._best(self.means(s), candidates, rng)

    @pick("explore", "Explore 1 in 10",
          "One pull in ten, pull a random arm instead of the best one.", "dice")
    def card_explore(self, s, candidates, player, rng):
        return rng.choice(candidates) if rng.random() < 0.1 else None

    @pick("ucb", "Be optimistic (UCB1)",
          "Score each arm as its average plus a bonus for how little you know it, then pull "
          "the top score. Untried arms come first.", "eye")
    def card_ucb(self, s, candidates, player, rng):
        t = s.n + 1
        means = self.means(s)
        scores = [ucb1_index(means[a], s.pulls[a], t) for a in range(self.arms)]
        return self._best(scores, candidates, rng)

    # ----------------------------------------------------------- presentation
    def action_label(self, s: BanditState, a: Action) -> str:
        if s.seed is None:
            return "draw the arms"
        if s.pending is not None:
            return "pays 1" if a == 1 else "pays 0"
        return f"pull arm {LETTERS[int(a)]}"

    def describe(self, s: BanditState, a: Action, player: int) -> str:
        return f"pulls arm {LETTERS[int(a)]}"

    def describe_chance(self, s: BanditState, a: Action) -> str:
        if s.seed is None:
            return "draws the hidden odds"
        arm = LETTERS[s.pending]
        return f"arm {arm} pays 1" if a == 1 else f"arm {arm} pays nothing"

    def status(self, s: BanditState, viewer: int | None) -> str:
        total = self.p["pulls"]
        if self.is_terminal(s):
            best = max(range(self.arms), key=lambda i: s.probs[i])
            return (f"Done: {int(s.total)} payouts in {total} pulls. Best arm was "
                    f"{LETTERS[best]} (p = {s.probs[best]:.2f})")
        if s.seed is None or s.pending is not None:
            return "The machine whirs..."
        return f"Pull {s.n + 1} of {total}: choose an arm"

    def scene(self, s: BanditState, viewer: int | None) -> dict:
        over = self.is_terminal(s)
        acting = not over and s.seed is not None and s.pending is None
        means = self.means(s)
        best = max(range(self.arms), key=lambda i: s.probs[i]) if over else None
        arms = []
        for i in range(self.arms):
            sub = f"{s.wins[i]} of {s.pulls[i]} paid"
            if over:
                sub += f" | true p = {s.probs[i]:.2f}"
            arms.append(scene.arm(f"Arm {LETTERS[i]}", pulls=s.pulls[i],
                                  mean=round(means[i], 3) if s.pulls[i] else None,
                                  action=i if acting else None,
                                  tone="good" if i == best else "", sub=sub))
        board = scene.arms(arms, caption="Average payout so far. The true odds stay hidden "
                                         "until the last pull.")
        me = scene.player("You", score=f"{int(s.total)}", sub=f"pull {s.n} of "
                          f"{self.p['pulls']}", active=acting, owner=0)
        return scene.scene([board], players=[me], status=self.status(s, viewer))
