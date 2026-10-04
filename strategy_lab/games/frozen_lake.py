"""FrozenLake: cross a frozen lake without falling through a hole.

A grid world from Gymnasium's toy-text set
(https://gymnasium.farama.org/environments/toy_text/frozen_lake/). The agent
starts at ``S`` and walks to ``G``. Holes (``H``) end the episode. The reward
is 1 for reaching the goal and 0 otherwise.

On the *slippery* lake, as in Gymnasium, the agent moves in the intended
direction with probability 1/3 and in each of the two perpendicular
directions with probability 1/3. Each move is therefore a chance node after
the decision: the engine asks "where does the ice take you?". Even the best
policy reaches the goal only about 74% of the time on 4x4, which is why the
lake is the standard first problem for value iteration and Q-learning.

The maps are the two Gymnasium presets, with ``.`` for frozen tiles. The
step limits follow Gymnasium's registered time limits: 100 steps on 4x4 and
200 on 8x8.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Model, Param, Rulebook
from strategy_lab.families.mdp import GridWorld

MAPS = {
    "4x4": ("S...",
            ".H.H",
            "...H",
            "H..G"),
    "8x8": ("S.......",
            "........",
            "...H....",
            ".....H..",
            "...H....",
            ".HH...H.",
            ".H..H.H.",
            "...H...G"),
}


class FrozenLake(GridWorld):
    id = "frozenlake"
    name = "FrozenLake"
    icon = "snowflake"
    tagline = "Walk the frozen lake to the goal. The ice has a mind of its own."
    chapter = "learning"
    order = 20
    concepts = ("mdp", "markov-property", "reward-return", "value-function", "bellman",
                "value-iteration", "discount", "q-learning")

    params = {
        "size": Param("4x4", "Map", "4x4 has 16 tiles, 8x8 has 64 and many more holes.",
                      choices=("4x4", "8x8")),
        "slippery": Param(True, "Slippery", "On slippery ice the move you pick happens "
                                            "1 time in 3. Otherwise you slide sideways."),
    }
    rewards = {"G": 1.0}
    win_return = 1.0

    rulebook = Rulebook(
        summary="Cross a frozen lake from the start to the goal. Holes in the ice end "
                "the game.",
        steps=(
            ("The lake", "A grid of ice. You start in the top-left corner. The goal is in "
                         "the bottom-right corner. Some tiles are holes."),
            ("A move", "Pick up, right, down or left. On slippery ice the move you pick "
                       "happens only 1 time in 3. Otherwise the ice carries you to one of "
                       "the two sides, each with probability 1/3."),
            ("Reward", "Reaching the goal pays 1. Falling into a hole pays 0 and ends the "
                       "game, and so does running out of steps."),
        ),
        extra=(
            ("Step limit", "The game stops after 100 steps on 4x4 and 200 on 8x8, the "
                           "time limits Gymnasium registers for these maps. You can "
                           "change the limit."),
            ("Edges", "A move off the edge leaves you where you are."),
        ),
        source="https://gymnasium.farama.org/environments/toy_text/frozen_lake/",
    )

    models = (
        Model("index", "Cell index (known map)", True,
              state="your cell index, 0 to 15 on 4x4",
              size="16 states (64 on 8x8)",
              actions="up / right / down / left",
              transition="stochastic on slippery ice: three outcomes with probability 1/3 each",
              reward="+1 at the goal, 0 otherwise; gamma close to 1",
              note="Slipping makes the transition random, not the state incomplete: "
                   "still fully Markov. Q-learning needs only a 16 x 4 table."),
        Model("time", "Cell index and steps left", True,
              state="your cell index plus how many steps remain before the limit",
              size="16 x 100 states",
              actions="up / right / down / left",
              transition="as above, and the counter ticks down every move",
              reward="+1 at the goal, 0 otherwise",
              note="The time limit is part of the game, so strictly the cell alone is "
                   "not enough near the end. Standard practice ignores it, as the "
                   "Gymnasium time-limit wrapper does."),
        Model("explored", "Coordinates and explored tiles", "approx",
              state="your row and column plus the set of tiles seen so far, for a map the "
                    "agent does not know",
              size="grows with the map",
              actions="up / right / down / left",
              transition="as above",
              reward="+1 at the goal, 0 otherwise",
              note="With an unknown map, which tiles are holes is information that "
                   "lives in the history. The agent has to fold that history into the state."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Walks in random directions.", 1, icon="dice"),
        Bot("cleo", "Compass Cleo", "Always steps toward the goal along the shortest route "
            "that avoids holes.", 2, cards=("goal",), icon="compass"),
        Bot("carl", "Careful Carl", "Avoids tiles next to holes and walls, then heads for "
            "the goal.", 3, cards=("safe", "bump", "goal"), icon="shield"),
        Bot("vera", "Planner Vera", "Knows the map and the slip odds. Plays the plan from "
            "value iteration.", 4, cards=("plan",), icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("goal", "Reach the goal", "win", 2),
        Challenge("rl", "Open the Learn lens", "lens", 1, lens="rl"),
    )

    def make_layout(self):
        return MAPS[self.p["size"]]

    def default_steps(self) -> int:
        return 200 if self.p["size"] == "8x8" else 100
