"""Concept cards: the cheatsheet.

Every idea the lab teaches is one :class:`Concept`. Games list the concept
ids they teach (``Game.concepts``); finishing such a game adds the card to
your cheatsheet. The cheatsheet is reachable from the game menu at any
time, and the Sphinx docs render the same cards.

Text conventions: ``body`` is short Markdown (paragraphs, ``**bold**``,
``*italic*``, lists). ``formula`` is LaTeX without ``$`` delimiters.
Keep cards short: one idea, one formula, one example.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    id: str
    title: str
    chapter: str
    #: One sentence. Shown on the card front.
    short: str
    #: Two to four short paragraphs of Markdown.
    body: str = ""
    #: LaTeX, no ``$``.
    formula: str = ""
    #: A worked example, ideally from a lab game.
    example: str = ""
    related: tuple[str, ...] = ()

    def to_json(self) -> dict:
        d = dict(self.__dict__)
        d["related"] = list(self.related)
        return d


def _c(id, title, chapter, short, **kw) -> Concept:
    return Concept(id, title, chapter, short, **kw)


#: All concept cards, in teaching order. Bodies are filled in by
#: :mod:`strategy_lab.learn.concept_texts` when present.
CONCEPTS: tuple[Concept, ...] = (
    # -- the lab itself ------------------------------------------------------
    _c("policy", "Policy", "chance",
       "A policy is a complete strategy: for every situation, what you would do."),
    _c("rule-cards", "Rule cards", "trees",
       "A policy written as an ordered stack of simple if-then rules."),
    _c("simulation", "Simulation", "chance",
       "Play many games fast to measure a strategy instead of guessing."),
    # -- chance ----------------------------------------------------------------
    _c("probability", "Probability", "chance",
       "How often something happens, as a number between 0 and 1."),
    _c("independence", "Independence", "chance",
       "Dice have no memory: the last roll does not change the next one."),
    _c("expected-value", "Expected value", "chance",
       "The average result per try if you repeated a choice forever."),
    _c("variance", "Variance", "chance",
       "How far single results scatter around the average."),
    _c("law-of-large-numbers", "Law of large numbers", "chance",
       "Over many games, the average result settles near the expected value."),
    _c("distribution-of-sums", "Sums of dice", "chance",
       "Adding dice makes middle totals common and extreme totals rare."),
    _c("entropy", "Entropy", "chance",
       "The average surprise of a random event, measured in bits."),
    # -- trees -----------------------------------------------------------------
    _c("game-tree", "Game tree", "trees",
       "Every possible continuation of a game, drawn as branching moves."),
    _c("branching-factor", "Branching factor", "trees",
       "How many moves you have on average: the tree grows by this factor per turn."),
    _c("backward-induction", "Backward induction", "trees",
       "Solve a game from the end: the last mover's choice is easy, then work back."),
    _c("minimax", "Minimax", "trees",
       "Assume the opponent picks your worst outcome; pick the best of those."),
    _c("winning-position", "Winning and losing positions", "trees",
       "A position is lost if every move leads to a won position for the opponent."),
    _c("symmetry", "Symmetry", "trees",
       "Positions that are rotations or mirrors of each other have the same value."),
    _c("solved-game", "Solved game", "trees",
       "A game whose value with perfect play is known: win, draw or loss."),
    _c("monte-carlo", "Monte Carlo", "trees",
       "Estimate a value by playing many random games and averaging the results."),
    _c("mcts", "Monte Carlo tree search", "trees",
       "Grow the game tree where random playouts look promising, then pick the most visited move."),
    _c("heuristic", "Heuristic", "trees",
       "A quick guess of a position's value when the full tree is too big."),
    # -- dice and choice ---------------------------------------------------------
    _c("expectimax", "Expectimax", "dice-and-choice",
       "Minimax with dice: average over chance, maximize over your own choices."),
    _c("risk", "Risk", "dice-and-choice",
       "Choosing between a sure thing and a gamble with the same or better average."),
    _c("luck-vs-skill", "Luck versus skill", "dice-and-choice",
       "How much a better policy shifts the win rate, compared to the dice."),
    # -- outguess -------------------------------------------------------------------
    _c("zero-sum", "Zero-sum game", "outguess",
       "What one player wins, the other loses."),
    _c("best-response", "Best response", "outguess",
       "The strategy that does best against a fixed strategy of the opponent."),
    _c("dominant-strategy", "Dominant strategy", "outguess",
       "A choice that is better no matter what the opponent does."),
    _c("nash-equilibrium", "Nash equilibrium", "outguess",
       "Strategies where no player gains by changing only their own."),
    _c("mixed-strategy", "Mixed strategy", "outguess",
       "Randomizing on purpose so the opponent cannot read you."),
    _c("exploitability", "Exploitability", "outguess",
       "How much a perfect opponent would win against your strategy."),
    _c("regret", "Regret", "outguess",
       "How much better another action would have done. Learning to reduce it "
       "finds equilibria."),
    _c("repeated-game", "Repeated game", "outguess",
       "The same game played many rounds: the future shadow can make cooperation pay."),
    _c("tit-for-tat", "Tit-for-Tat", "outguess",
       "Cooperate first, then copy whatever the opponent did last round."),
    _c("social-dilemma", "Social dilemma", "outguess",
       "Each player's best choice leads to a worse result for everyone."),
    _c("coordination", "Coordination game", "outguess",
       "Several equilibria exist; the problem is agreeing on one."),
    # -- hidden ----------------------------------------------------------------------
    _c("imperfect-information", "Imperfect information", "hidden",
       "Some facts of the game state are hidden from some players."),
    _c("information-set", "Information set", "hidden",
       "All positions a player cannot tell apart from what they know."),
    _c("belief", "Belief", "hidden",
       "A probability distribution over the hidden facts, updated by what you see."),
    _c("bluffing", "Bluffing", "hidden",
       "Acting strong with a weak hand, in the right proportion."),
    # -- learning --------------------------------------------------------------------
    _c("mdp", "Markov decision process", "learning",
       "States, actions, transition probabilities and rewards: the RL model of a task."),
    _c("markov-property", "Markov property", "learning",
       "The present state holds everything needed to predict the future."),
    _c("reward-return", "Reward and return", "learning",
       "Reward is the score of one step; return is the sum over an episode."),
    _c("discount", "Discount factor", "learning",
       "Future rewards count a bit less: gamma between 0 and 1."),
    _c("value-function", "Value function", "learning",
       "The expected return from a state when following a policy."),
    _c("bellman", "Bellman equation", "learning",
       "A state's value is the reward now plus the discounted value of what follows."),
    _c("value-iteration", "Value iteration", "learning",
       "Apply the Bellman update to every state until the values stop changing."),
    _c("ucb", "Upper confidence bound", "learning",
       "Pick the action whose optimistic estimate is highest: optimism drives exploration."),
    _c("exploration", "Exploration vs exploitation", "learning",
       "Try new actions to learn, or use the best one known so far."),
    _c("q-learning", "Q-learning", "learning",
       "Learn the value of each action in each state from experience alone."),
    _c("policy-entropy", "Policy entropy", "learning",
       "How random a policy is; high entropy explores, low entropy exploits."),
    # -- society ------------------------------------------------------------------------
    _c("multi-agent", "Multi-agent play", "society",
       "With three or more players, your rival's rival can be your ally."),
    _c("negotiation", "Negotiation", "society",
       "A trade helps both sides; the question is who it helps more."),
)


def _with_texts() -> tuple[Concept, ...]:
    """Merge long-form texts from :mod:`concept_texts` if that module exists."""
    try:
        from strategy_lab.learn.concept_texts import TEXTS
    except ImportError:
        return CONCEPTS
    out = []
    for c in CONCEPTS:
        extra = TEXTS.get(c.id, {})
        out.append(Concept(**{**c.__dict__, **extra}))
    return tuple(out)


def all_concepts() -> tuple[Concept, ...]:
    return _with_texts()


def concept_ids() -> set[str]:
    return {c.id for c in CONCEPTS}
