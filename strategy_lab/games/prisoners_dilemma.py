"""The Prisoner's Dilemma: when the best choice for each hurts both.

Defecting beats cooperating whatever the other player does (a *dominant
strategy*), so the only Nash equilibrium is mutual defection, which pays
less than mutual cooperation. Repeated play is where it gets interesting:
a partner who remembers can answer defection with defection, and cooperation
can pay. Tit-for-Tat and Grim Trigger are two classic memories.

Payoffs follow Axelrod's tournaments: temptation T=5, reward R=3,
punishment P=1, sucker S=0, with T > R > P > S and 2R > T + S, so that
taking turns at exploiting each other never beats steady cooperation.

The family supplies the hidden commits, the scene and the shared cards.
This file adds the table, the cards of the PD folklore (open friendly, never
forgive, defect on the last round) and the four classic partners.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Model, Param, Rulebook, pick
from strategy_lab.families.matrix import MatrixGame

COOPERATE, DEFECT = 0, 1
#: Temptation, reward, punishment, sucker (the payoffs are the row player's).
T, R, P, S = 5, 3, 1, 0


class PrisonersDilemma(MatrixGame):
    id = "prisonersdilemma"
    name = "Prisoner's Dilemma"
    icon = "handshake"
    tagline = "Betray for the bigger prize, and both end up poorer."
    chapter = "outguess"
    order = 20
    concepts = ("dominant-strategy", "nash-equilibrium", "social-dilemma", "best-response",
                "repeated-game", "tit-for-tat", "regret")

    action_names = ("Cooperate", "Defect")
    payoff_table = (((R, R), (S, T)),
                    ((T, S), (P, P)))
    params = {"rounds": Param(10, "Rounds", "How many times you meet the same partner. "
                                            "Your return is your total payoff.", min=1, max=100)}

    rulebook = Rulebook(
        summary="Two players each choose to cooperate or defect, at the same time. "
                "Mutual cooperation pays well, but defecting against a cooperator pays more.",
        steps=(
            ("Choose", "Each round, both players pick cooperate or defect in secret."),
            ("Payoffs", "Both cooperate: 3 each. Both defect: 1 each. One defects against "
                        "a cooperator: 5 for the defector, 0 for the cooperator."),
            ("Repeat", "You meet the same partner for the number of rounds you set. Your "
                       "return is your total payoff."),
        ),
        extra=(
            ("Hidden moves", "The engine moves one seat at a time. The first player locks "
                             "in a choice that stays hidden. The second player locks in "
                             "without seeing it. Then the round is revealed."),
            ("Known length", "Both players know how many rounds there are. That matters "
                             "in the last round, when nothing is left to punish a defection."),
        ),
        source="https://en.wikipedia.org/wiki/Prisoner%27s_dilemma",
    )

    models = (
        Model("last", "Last round only", "approx",
              state="the pair of moves revealed in the last round",
              actions="cooperate / defect",
              reward="your payoff each round, summed over the rounds",
              size="4 states (plus the first round)",
              transition="the table pays you at once, the partner's policy chooses the "
                         "next state",
              note="Exactly the memory Tit-for-Tat needs, so it is Markov against that "
                   "partner. It cannot tell a partner who defected once long ago from "
                   "one who never did, so Grim Trigger breaks it."),
        Model("betrayed", "Last round and 'has the partner ever defected?'", "approx",
              state="the last round plus one bit: did the partner ever defect",
              actions="cooperate / defect",
              reward="your payoff each round, summed over the rounds",
              size="8 states",
              transition="the table pays you at once, the partner's policy chooses the "
                         "next state",
              note="Enough for Tit-for-Tat, Grim Trigger and the constant partners. A "
                   "partner who counts defections or forgives after k rounds still breaks it."),
        Model("history", "Full history of rounds", True,
              state="every revealed round in order",
              actions="cooperate / defect",
              reward="your payoff each round, summed over the rounds",
              size="4^t after t rounds",
              transition="the partner's policy maps this history to their next move",
              note="Always Markov, but it grows with every round. The round number also "
                   "matters: the last round is a different game."),
    )

    bots = (
        Bot("pat", "Pushover Pat", "Always cooperates, whatever you do.", 1,
            cards=("always-cooperate",), icon="smile"),
        Bot("carl", "Cold Carl", "Always defects. Never trusts, never loses a pairing.", 2,
            cards=("always-defect",), icon="sword"),
        Bot("tess", "Tit-for-Tat Tess", "Opens friendly, then does what you did last round.",
            3, cards=("open-nice", "copy"), icon="handshake"),
        Bot("gordon", "Grim Gordon", "Cooperates until you defect once. Then never again.",
            4, cards=("grim",), icon="shield"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("coop", "Earn 30 points in one game", "score", 1, value=30),
        Challenge("nash", "Open the Nash lens", "lens", 1, lens="nash"),
        Challenge("beat-tess", "Out-score Tit-for-Tat Tess", "win", 2, bot="tess"),
        Challenge("stack-gordon", "Build a card stack that out-scores Grim Gordon in 90% "
                  "of 100 games", "sim", 3, bot="gordon", metric="winrate", value=0.9),
    )

    # ----------------------------------------------------------- rule cards
    @pick("always-cooperate", "Always cooperate", "Cooperate every round, whatever happens.",
          "handshake")
    def card_always_cooperate(self, s, candidates, player, rng):
        return COOPERATE if COOPERATE in candidates else None

    @pick("always-defect", "Always defect", "Defect every round. Never the sucker, never "
          "the winner of the long game.", "sword")
    def card_always_defect(self, s, candidates, player, rng):
        return DEFECT if DEFECT in candidates else None

    @pick("open-nice", "Open friendly", "Cooperate in round 1, to offer a deal.", "smile")
    def card_open_nice(self, s, candidates, player, rng):
        return COOPERATE if not s.rounds and COOPERATE in candidates else None

    @pick("grim", "Never forgive",
          "Cooperate until they defect once. After that, defect for the rest of the game.",
          "shield")
    def card_grim(self, s, candidates, player, rng):
        betrayed = DEFECT in self.opponent_actions(s, player)
        move = DEFECT if betrayed else COOPERATE
        return move if move in candidates else None

    @pick("finale", "Defect in the last round",
          "In the last round nothing is left to punish a defection, so defecting pays most.",
          "flag")
    def card_finale(self, s, candidates, player, rng):
        last_round = len(s.rounds) == self.p["rounds"] - 1
        return DEFECT if last_round and DEFECT in candidates else None

    # ---------------------------------------------------------- presentation
    def insight(self, stats: dict) -> str | None:
        bot = self.bot(stats["bot"])
        mine, theirs = stats["meanReturns"][0], stats["meanReturns"][1]
        both = R * self.p["rounds"]
        return (f"You averaged {mine:.1f} points and {bot.name} {theirs:.1f}. "
                f"Two steady cooperators would earn {both} each. Beating a partner head to "
                "head and earning a lot are different goals.")
