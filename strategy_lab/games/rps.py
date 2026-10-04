"""Rock-Paper-Scissors: the smallest game with no best move.

Every move loses to another one, so a fixed choice can always be punished.
The only unbeatable strategy is to play all three moves with probability
1/3, a *mixed* Nash equilibrium. This is the entry point to the "outguess"
chapter: everything generic (hidden commits, scene, equilibrium solver, the
"copy", "hunt", "mix", "wsls" and "outthink" cards) comes from
:class:`~strategy_lab.families.matrix.MatrixGame`. This file adds the 3x3
table, three RPS-specific cards and the bots.

The hunter bot counts your moves and plays the best answer to your mix. It
cannot be fooled by a stack of fixed rules, and it punishes every habit.
That is the lesson in entropy: the less predictable you are, the less it
gets. A card stack with the ``outthink`` card beats it, because the hunter's
own habit (best-reply to your counts) is predictable too.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Param, Rulebook, pick
from strategy_lab.families.matrix import MatrixGame

ROCK, PAPER, SCISSORS = 0, 1, 2


def beats(a: int, b: int) -> bool:
    """Does move ``a`` beat move ``b``? Paper beats rock, scissors beat paper, rock beats scissors."""
    return (a - b) % 3 == 1


def _payoff(i: int, j: int) -> tuple[int, int]:
    if i == j:
        return (0, 0)
    return (1, -1) if beats(i, j) else (-1, 1)


class RockPaperScissors(MatrixGame):
    id = "rps"
    name = "Rock-Paper-Scissors"
    icon = "scissors"
    tagline = "No move beats them all. Your only defence is to be unreadable."
    chapter = "outguess"
    order = 10
    concepts = ("zero-sum", "best-response", "mixed-strategy", "nash-equilibrium",
                "exploitability", "entropy")

    action_names = ("Rock", "Paper", "Scissors")
    payoff_table = tuple(tuple(_payoff(i, j) for j in range(3)) for i in range(3))
    params = {"rounds": Param(20, "Rounds", "How many times you throw. Your return is "
                                            "wins minus losses.", min=1, max=100)}

    rulebook = Rulebook(
        summary="Both players pick rock, paper or scissors at the same time. "
                "Rock beats scissors, scissors beat paper, paper beats rock.",
        steps=(
            ("Choose", "Each round, both players pick one of three moves in secret."),
            ("Reveal", "Both picks show at once. The winner scores +1, the loser -1. "
                       "Equal picks score 0 for both."),
            ("Repeat", "The game lasts the number of rounds you set. Your return is the "
                       "sum of the round payoffs."),
        ),
        extra=(
            ("Hidden moves", "The engine moves one seat at a time. The first player locks "
                             "in a choice that stays hidden. The second player locks in "
                             "without seeing it. Then the round is revealed."),
            ("Repeated game", "The same one-round game is played again and again, so "
                              "patterns in your choices can be counted and punished."),
        ),
        source="https://en.wikipedia.org/wiki/Rock_paper_scissors",
    )

    bots = (
        Bot("rocky", "Rocky Rock", "Throws rock. Always. It is his favourite.", 1,
            cards=("rock",), icon="mountain"),
        Bot("cleo", "Copycat Cleo", "Throws whatever you threw last round.", 2,
            cards=("copy",), icon="mirror"),
        Bot("hank", "Hunter Hank", "Counts your throws and plays the best answer to your "
            "habits.", 3, cards=("hunt",), icon="target"),
        Bot("nina", "Nash Nina", "Rock, paper or scissors with equal odds. Cannot be read "
            "and cannot be beaten.", 4, cards=("mix",), icon="dice"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-rocky", "Beat Rocky Rock", "win", 1, bot="rocky"),
        Challenge("nash", "Open the Nash lens", "lens", 1, lens="nash"),
        Challenge("beat-hank", "Beat Hunter Hank", "win", 2, bot="hank"),
        Challenge("stack-hank", "Build a card stack that beats Hunter Hank in 70% of "
                  "100 games", "sim", 3, bot="hank", metric="winrate", value=0.7),
    )

    # ----------------------------------------------------------- rule cards
    @pick("rock", "Always rock", "Throw rock every round. Simple, and very easy to read.",
          "mountain")
    def card_rock(self, s, candidates, player, rng):
        return ROCK if ROCK in candidates else None

    @pick("beat-last", "Beat their last move",
          "Assume they repeat themselves: throw what beats their last throw.", "sword")
    def card_beat_last(self, s, candidates, player, rng):
        theirs = self.opponent_actions(s, player)
        if not theirs:
            return None
        move = (theirs[-1] + 1) % 3
        return move if move in candidates else None

    @pick("cycle", "Walk the cycle", "Rock, then paper, then scissors, then rock again. "
          "Looks random, is not.", "shuffle")
    def card_cycle(self, s, candidates, player, rng):
        mine = self.own_actions(s, player)
        move = (mine[-1] + 1) % 3 if mine else ROCK
        return move if move in candidates else None

    # ---------------------------------------------------------- presentation
    def outcome_text(self, a0: int, a1: int) -> str:
        if a0 == a1:
            return "tie"
        winner, loser = (a0, a1) if beats(a0, a1) else (a1, a0)
        names = self.action_names
        return f"{names[winner]} beats {names[loser]} (+1)"

    def insight(self, stats: dict) -> str | None:
        bot = self.bot(stats["bot"])
        mean = stats["meanReturns"][0]
        if bot.id == "nina":
            return ("Nina mixes one third each. Every stack scores about 0 against her: "
                    "a mixed equilibrium cannot be exploited, only matched.")
        if mean >= 1.0:
            return (f"Your stack out-guesses {bot.name}: +{mean:.1f} points per game. "
                    "It found a pattern the bot cannot hide.")
        if mean <= -1.0:
            return (f"{bot.name} reads your stack: {mean:.1f} points per game. A fixed "
                    "pattern is a gift to a bot that counts. Try the equilibrium mix, or "
                    "think a level deeper than the hunter.")
        return "Close to even. Neither side found an edge."
