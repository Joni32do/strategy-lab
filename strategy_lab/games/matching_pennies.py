"""Matching Pennies: the cleanest zero-sum game with no pure equilibrium.

Each player hides a coin, heads or tails. The Matcher wins if both coins
agree, the Mismatcher wins if they differ. Whatever one player does
predictably, the other punishes, so the only equilibrium is a coin flip for
both. Unlike Rock-Paper-Scissors the two seats want different things, which
makes it a good place to read a payoff matrix from both sides.

The family supplies everything else: hidden commits, the scene, the
equilibrium solver (closed form for 2x2) and the shared rule cards.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Param, Rulebook, pick
from strategy_lab.families.matrix import MatrixGame

HEADS, TAILS = 0, 1


class MatchingPennies(MatrixGame):
    id = "matchingpennies"
    name = "Matching Pennies"
    icon = "coin"
    tagline = "Match the coin or dodge it. Whoever is predictable loses."
    chapter = "outguess"
    order = 15
    concepts = ("zero-sum", "mixed-strategy", "nash-equilibrium", "best-response",
                "exploitability", "entropy")

    seat_names = ("Matcher", "Mismatcher")
    action_names = ("Heads", "Tails")
    #: The Matcher (seat 0) wins when the coins agree, the Mismatcher when they differ.
    payoff_table = (((1, -1), (-1, 1)),
                    ((-1, 1), (1, -1)))
    params = {"rounds": Param(20, "Rounds", "How many coins you hide. Your return is "
                                            "rounds won minus rounds lost.", min=1, max=100)}

    rulebook = Rulebook(
        summary="Two players each hide a coin, heads or tails. The Matcher wins when the "
                "coins agree. The Mismatcher wins when they differ.",
        steps=(
            ("Choose", "Each round, both players pick heads or tails in secret."),
            ("Reveal", "Both coins show at once. Same side: the Matcher scores +1 and the "
                       "Mismatcher -1. Different sides: the other way round."),
            ("Repeat", "The game lasts the number of rounds you set. Your return is the "
                       "sum of the round payoffs."),
        ),
        extra=(
            ("Hidden moves", "The engine moves one seat at a time. The Matcher locks in a "
                             "choice that stays hidden. The Mismatcher locks in without "
                             "seeing it. Then the round is revealed."),
            ("Repeated game", "The same one-round game is played again and again, so "
                              "patterns in your choices can be counted and punished."),
        ),
        source="https://en.wikipedia.org/wiki/Matching_pennies",
    )

    bots = (
        Bot("harry", "Heads-up Harry", "Always shows heads.", 1, cards=("heads",),
            icon="coin"),
        Bot("cleo", "Copycat Cleo", "Shows what you showed last round.", 2,
            cards=("copy",), icon="mirror"),
        Bot("hank", "Hunter Hank", "Counts your coins and plays the best answer to your "
            "habit.", 3, cards=("hunt",), icon="target"),
        Bot("nell", "Nash Nell", "Flips a fair coin. Nothing to read, nothing to beat.", 4,
            cards=("mix",), icon="dice"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-cleo", "Beat Copycat Cleo", "win", 1, bot="cleo"),
        Challenge("nash", "Open the Nash lens", "lens", 1, lens="nash"),
        Challenge("beat-hank", "Beat Hunter Hank", "win", 2, bot="hank"),
        Challenge("stack-hank", "Build a card stack that beats Hunter Hank in 70% of "
                  "100 games", "sim", 3, bot="hank", metric="winrate", value=0.7),
    )

    # ----------------------------------------------------------- rule cards
    @pick("heads", "Always heads", "Show heads every round.", "coin")
    def card_heads(self, s, candidates, player, rng):
        return HEADS if HEADS in candidates else None

    @pick("flip", "Flip their last move", "Show the opposite of what they showed last round.",
          "shuffle")
    def card_flip(self, s, candidates, player, rng):
        theirs = self.opponent_actions(s, player)
        if not theirs:
            return None
        move = 1 - theirs[-1]
        return move if move in candidates else None

    # ---------------------------------------------------------- presentation
    def outcome_text(self, a0: int, a1: int) -> str:
        names = self.action_names
        verdict = "match" if a0 == a1 else "no match"
        winner = self.seat_label(0 if a0 == a1 else 1)
        return f"{names[a0]} and {names[a1]}: {verdict}, {winner} scores +1"

    def insight(self, stats: dict) -> str | None:
        bot = self.bot(stats["bot"])
        mean = stats["meanReturns"][0]
        if bot.id == "nell":
            return ("A fair coin cannot be read. Against Nell every stack averages 0, "
                    "which is the value of the game.")
        if mean >= 1.0:
            return f"Your stack finds a pattern in {bot.name}: +{mean:.1f} points per game."
        if mean <= -1.0:
            return (f"{bot.name} reads your stack: {mean:.1f} points per game. Anything "
                    "you repeat or alternate is a habit, and habits get counted.")
        return "Close to even. Neither side found an edge."
