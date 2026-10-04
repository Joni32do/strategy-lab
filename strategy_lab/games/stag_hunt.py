"""The Stag Hunt: trust is the whole game.

Two hunters each choose stag or hare. A stag needs both of them and feeds
both well. A hare can be caught alone and is a safe, smaller meal. So there
are two pure Nash equilibria: both stag (best for both, but risky) and both
hare (safe, but poorer). There is also a mixed equilibrium in which each
hunts stag with probability 3/4. The problem is not what is rational for one
player but which equilibrium both will pick: a *coordination* game.

The payoffs are one concrete choice inside the general form a > b >= d > c
of the Wikipedia article: a = 4 (stag together), b = d = 3 (a hare, whatever
the other does) and c = 0 (a lone stag hunter). The mixed equilibrium puts
probability (d - c) / (a - b - c + d) = 3/4 on stag.

The family supplies hidden commits, the scene and the shared cards. This
file adds the table, three cards and the four partners.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Param, Rulebook, pick
from strategy_lab.families.matrix import MatrixGame

STAG, HARE = 0, 1


class StagHunt(MatrixGame):
    id = "staghunt"
    name = "Stag Hunt"
    icon = "deer"
    tagline = "Hunt the stag together, or play it safe with a hare. Do you trust them?"
    chapter = "outguess"
    order = 30
    concepts = ("coordination", "nash-equilibrium", "best-response", "mixed-strategy",
                "repeated-game")

    action_names = ("Stag", "Hare")
    #: Both stag: 4 each. A hare is worth 3 whatever the other does. A lone stag: 0.
    payoff_table = (((4, 4), (0, 3)),
                    ((3, 0), (3, 3)))
    params = {"rounds": Param(10, "Rounds", "How many hunts you go on together. Your return "
                                            "is your total payoff.", min=1, max=100)}

    rulebook = Rulebook(
        summary="Two hunters each choose stag or hare at the same time. A stag takes both "
                "hunters. A hare can be caught alone.",
        steps=(
            ("Choose", "Each round, both hunters pick stag or hare in secret."),
            ("Payoffs", "Both stag: 4 each. A hare pays 3 whatever the other does. A stag "
                        "hunter whose partner went for the hare gets 0."),
            ("Repeat", "You hunt with the same partner for the number of rounds you set. "
                       "Your return is your total payoff."),
        ),
        extra=(
            ("Hidden moves", "The engine moves one seat at a time. The first hunter locks "
                             "in a choice that stays hidden. The second locks in without "
                             "seeing it. Then the round is revealed."),
            ("Payoff numbers", "Stag-stag 4, hare 3, lone stag 0 fit the general form "
                               "a > b >= d > c of the article. Only that order decides "
                               "which cells are equilibria."),
        ),
        source="https://en.wikipedia.org/wiki/Stag_hunt",
    )

    bots = (
        Bot("hana", "Hare Hana", "Always goes for the hare. Safe and steady.", 1,
            cards=("always-hare",), icon="rabbit"),
        Bot("sam", "Stag Sam", "Always hunts the stag, hoping you join.", 2,
            cards=("always-stag",), icon="deer"),
        Bot("cy", "Copycat Cy", "Opens with the stag, then does what you did last round.",
            3, cards=("open-stag", "copy"), icon="mirror"),
        Bot("max", "Mixer Max", "Plays the mixed equilibrium: stag 3 times in 4. Against "
            "another mixer, stag and hare both pay 3 a round.", 4, cards=("mix",),
            icon="dice"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("together", "Hunt stag together: earn 40 points in one game", "score", 2,
                  value=40),
        Challenge("nash", "Open the Nash lens", "lens", 1, lens="nash"),
        Challenge("draw-hana", "Draw with Hare Hana: no stag hunter can beat her", "draw", 1,
                  bot="hana"),
    )

    # ----------------------------------------------------------- rule cards
    @pick("always-stag", "Always stag", "Hunt the stag every round and hope they follow.",
          "deer")
    def card_always_stag(self, s, candidates, player, rng):
        return STAG if STAG in candidates else None

    @pick("always-hare", "Always hare", "Go for the hare every round. A sure 3.", "rabbit")
    def card_always_hare(self, s, candidates, player, rng):
        return HARE if HARE in candidates else None

    @pick("open-stag", "Open with the stag", "Hunt the stag in round 1, to signal trust.",
          "handshake")
    def card_open_stag(self, s, candidates, player, rng):
        return STAG if not s.rounds and STAG in candidates else None

    # ---------------------------------------------------------- presentation
    def insight(self, stats: dict) -> str | None:
        bot = self.bot(stats["bot"])
        mine, theirs = stats["meanReturns"][0], stats["meanReturns"][1]
        top = 4 * self.p["rounds"]
        return (f"You averaged {mine:.1f} points and {bot.name} {theirs:.1f}. "
                f"Stag together would pay {top} each. Hare is safe, but it caps you at "
                f"{3 * self.p['rounds']}.")
