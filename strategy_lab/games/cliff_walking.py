"""Cliff Walking: the shortest path is the dangerous one.

Sutton and Barto, Reinforcement Learning: An Introduction, Example 6.6
(http://incompleteideas.net/book/RLbook2020.pdf), also in Gymnasium
(https://gymnasium.farama.org/environments/toy_text/cliff_walking/). A 4x12
grid: the start is the bottom-left corner, the goal the bottom-right corner,
and the cells between them along the bottom edge are a cliff. Every move
costs -1. Stepping into the cliff costs -100 and puts you back on the start.
The episode ends at the goal.

The shortest route hugs the cliff (13 moves, return -13). The safe route
along the top takes 17 moves (return -17). With a slippery map or a learner
that sometimes explores at random, the cliff edge becomes risky: this is the
example that separates Q-learning, which learns the edge route, from SARSA,
which learns the safe one while it explores.

As in Gymnasium, the map is not slippery unless you switch it on.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Model, Rulebook, pick
from strategy_lab.families.mdp import GridWorld


class CliffWalking(GridWorld):
    id = "cliffwalking"
    name = "Cliff Walking"
    icon = "mountain"
    tagline = "Short path along the cliff edge or the long way round?"
    chapter = "learning"
    order = 30
    concepts = ("reward-return", "value-function", "discount", "exploration",
                "value-iteration", "q-learning")

    layout = ("............",
              "............",
              "............",
              "SCCCCCCCCCCG")
    rewards = {".": -1.0, "S": -1.0, "G": -1.0, "C": -100.0}
    free_tone = "safe"
    default_limit = 150
    win_return = -50.0

    rulebook = Rulebook(
        summary="Walk from the start to the goal along a cliff. Each step costs 1. "
                "Falling off the cliff costs 100 and sends you back to the start.",
        steps=(
            ("The map", "A grid of 4 rows and 12 columns. You start bottom-left, the goal "
                        "is bottom-right, and the tiles between them are the cliff."),
            ("A move", "Pick up, right, down or left. A move into the edge leaves you "
                       "where you are, and still costs 1."),
            ("Reward", "Every move costs -1. Stepping onto the cliff costs -100 and puts "
                       "you back on the start. The game ends at the goal."),
        ),
        extra=(
            ("Not slippery", "Moves go where you point, as in Gymnasium's default. Switch "
                             "on Slippery to make the edge dangerous."),
            ("Step limit", "The game also stops after 150 moves, so a lost walker "
                           "cannot go on forever."),
        ),
        source="http://incompleteideas.net/book/RLbook2020.pdf",
    )

    models = (
        Model("index", "Cell index", True,
              state="your cell index, 0 to 47 (the cliff and goal are never decision states)",
              size="37 decision states",
              actions="up / right / down / left",
              transition="deterministic unless the map is slippery",
              reward="-1 per move, -100 for the cliff; gamma = 1 works",
              note="Fully Markov. The reward structure, not the state, makes the problem "
                   "interesting: the best path passes right next to a -100 penalty."),
        Model("time", "Cell index and moves so far", "approx",
              state="your cell index plus the number of moves made",
              size="37 x 150 states",
              actions="up / right / down / left",
              transition="deterministic unless the map is slippery",
              reward="-1 per move, -100 for the cliff",
              note="The step limit makes time part of the true state, but the optimal "
                   "policy does not depend on it, so it is usually left out."),
        Model("row", "Row only", False,
              state="which of the 4 rows you are in",
              size="4 states",
              actions="up / right / down / left",
              transition="not decided by the state: the column decides where the cliff is",
              reward="-1 per move, -100 for the cliff",
              note="Too coarse: in the bottom row, the first column is safe and the "
                   "others are the cliff. A bad state design, and it shows why the "
                   "Markov property matters."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Walks in random directions. Falls a lot.", 1,
            icon="dice"),
        Bot("hana", "High-road Hana", "Climbs to the top row, crosses, and comes down at the "
            "end. Slow and safe.", 2, cards=("high-road",), icon="mountain"),
        Bot("eddie", "Edge Eddie", "Takes the shortest route, right along the cliff.", 3,
            cards=("goal",), icon="footprints"),
        Bot("vera", "Planner Vera", "Plays the plan from value iteration: the best route "
            "for the rules in force.", 4, cards=("plan",), icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("clean", "Reach the goal without falling", "win", 1),
        Challenge("safe", "Finish with a return of -17 or better", "score", 2, value=-17),
        Challenge("rl", "Open the Learn lens", "lens", 1, lens="rl"),
        Challenge("shortest", "Walk the shortest route: return -13", "score", 3, value=-13),
    )

    @pick("high-road", "Take the high road",
          "Climb to the top row first, cross to the far column, then come down. Longer, "
          "but far from the cliff.", "mountain")
    def card_high_road(self, s, candidates, player, rng):
        row, col = divmod(s.pos, self.cols)
        if col == self.cols - 1:
            want = "down"
        elif row > 0:
            want = "up"
        else:
            want = "right"
        return want if want in candidates else None
