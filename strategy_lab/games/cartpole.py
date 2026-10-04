"""CartPole: balance a pole by pushing a cart left or right.

Gymnasium's ``CartPole-v1`` through :class:`~strategy_lab.families.external.GymGame`.
The fruit fly of reinforcement learning: four numbers describe the world,
two actions move it, and every step the pole stays up earns +1 (at most 500).

Why the rule cards matter here: the three controllers below are the three
steps from naive to good, measured over 30 episodes with seeds 0..29.

=========================  ==================  ==========
card                       looks at            mean steps
=========================  ==================  ==========
"Lean with the pole"       angle only          about 39
"Follow the swing"         angular velocity    about 190
"Look ahead"               angle + velocity    500
=========================  ==================  ==========

Custom scene part ``cartpole``
------------------------------
::

    {"view": "cartpole",
     "x": 0.03,                # cart position (track runs from -xLimit to +xLimit)
     "theta": -0.01,           # pole angle in radians, 0 is upright, positive leans right
     "xLimit": 2.4,            # the episode ends if |x| exceeds this
     "thetaLimit": 0.2095,     # ... or if |theta| exceeds this (12 degrees)
     "steps": 17,              # steps survived so far (= reward so far)
     "done": false}

The four observation numbers also come as a stock ``scene.bars`` part and the two
actions as a ``scene.buttons`` part (``0`` push left, ``1`` push right).
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Model, Rulebook, avoid, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.external import GymGame, GymState

X_LIMIT = 2.4
THETA_LIMIT = 0.20943951023931953          # 12 degrees in radians
LEFT, RIGHT = 0, 1
OBS_LABELS = ("cart position", "cart velocity", "pole angle", "pole angular velocity")
#: Display range of each observation bar.
OBS_RANGE = (X_LIMIT, 3.0, round(THETA_LIMIT, 4), 3.0)


class CartPole(GymGame):
    id = "cartpole"
    name = "CartPole"
    icon = "scale"
    tagline = "Keep a pole upright on a cart. Four numbers, two buttons, +1 per step."
    chapter = "learning"
    order = 40
    concepts = ("mdp", "markov-property", "reward-return", "policy")
    env_id = "CartPole-v1"
    action_names = ("left", "right")
    seat_names = ("Controller",)
    #: One step per action, plus the reset: the 500-step cap fits easily.
    max_steps = 520

    rulebook = Rulebook(
        summary="A pole stands on a cart that rolls along a track. Push the cart left or "
                "right to keep the pole from falling.",
        steps=(
            ("The task", "Every step you push the cart left or right with a fixed force. "
                         "Physics moves the cart and tips the pole."),
            ("The reward", "You get +1 for every step the pole is still up. Your return is "
                           "the number of steps you survive."),
            ("Failure", "The episode ends when the pole leans more than 12 degrees or the "
                        "cart leaves the track (2.4 units from the middle)."),
            ("Success", "Survive 500 steps and the episode ends with the maximum return."),
        ),
        extra=(
            ("Start", "The first state is drawn at random (small numbers around zero). "
                      "The lab records that draw as a seed, so a game replays exactly."),
        ),
        source="https://gymnasium.farama.org/environments/classic_control/cart_pole/",
    )

    models = (
        Model("full", "Position + velocity + angle + angular velocity", True,
              state="[cart position, cart velocity, pole angle, pole angular velocity], "
                    "four continuous numbers",
              size="a continuous box in 4 dimensions",
              actions="push left / push right",
              transition="deterministic physics (Euler steps of 0.02 s)",
              reward="+1 per step until the pole falls or the cart leaves the track "
                     "(cap 500)",
              note="Markov: the four numbers predict the next four exactly."),
        Model("no-velocity", "Position + angle only", False,
              state="[cart position, pole angle] only",
              actions="push left / push right",
              reward="+1 per step until the pole falls or the cart leaves the track "
                     "(cap 500)",
              note="Two snapshots that look identical can be a pole swinging up and a pole "
                   "crashing down. The missing velocities are exactly one step of history: "
                   "the cleanest 'history is state' example in the lab."),
        Model("binned", "Discretized (binned) state", "approx",
              state="the 4 numbers cut into coarse bins (the classic tabular treatment)",
              size="bins^4 table cells",
              actions="push left / push right",
              reward="+1 per step until the pole falls or the cart leaves the track "
                     "(cap 500)",
              note="Markov up to the rounding error. Finer bins buy precision at the cost "
                   "of a much bigger table."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Pushes left or right at random. The pole lasts about "
            "20 steps.", 1, icon="dice"),
        Bot("lee", "Lean-in Lee", "Pushes toward wherever the pole leans. Sensible, and it "
            "falls over in about 40 steps.", 2, cards=("lean",), icon="snake"),
        Bot("sue", "Swing-watcher Sue", "Watches how fast the pole is tipping and pushes "
            "with it. About 190 steps.", 3, cards=("swing",), icon="timer"),
        Bot("pete", "Predicting Pete", "Adds the angle and the swing speed to look a "
            "moment ahead. Holds all 500 steps.", 4, cards=("predict",),
            icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play an episode to the end", "finish"),
        Challenge("hold-100", "Keep the pole up for 100 steps", "score", 1, value=100.0),
        Challenge("rl", "Open the learning lens", "lens", 1, lens="rl"),
        Challenge("hold-300", "Keep the pole up for 300 steps", "score", 2, value=300.0),
        Challenge("hold-500", "Survive all 500 steps", "score", 3, value=500.0),
    )

    # ------------------------------------------------------------ presentation
    def describe(self, s, a, player) -> str:
        return f"pushes the cart {self.action_names[int(a)]}"

    def scene(self, s: GymState, viewer):
        obs = self.obs_vector(s)
        if not obs:
            return scene.scene([scene.text("Starting...")], status=self.status(s, viewer))
        done = self.is_terminal(s)
        pole = scene.custom("cartpole", x=round(obs[0], 4), theta=round(obs[2], 4),
                            xLimit=X_LIMIT, thetaLimit=round(THETA_LIMIT, 4),
                            steps=len(s.actions), done=done)
        bars = scene.bars(
            [scene.bar(label, round(v, 3), min=-r, max=r,
                       tone="bad" if abs(v) > r and i in (0, 2) else "")
             for i, (label, v, r) in enumerate(zip(OBS_LABELS, obs, OBS_RANGE))],
            caption="What the controller sees")
        parts = [pole, bars]
        if not done:
            parts.append(scene.buttons([(LEFT, "Push left"), (RIGHT, "Push right")]))
        return scene.scene(parts, status=self.status(s, viewer))

    # -------------------------------------------------------------- rule cards
    @pick("lean", "Lean with the pole",
          "Push toward the side the pole leans to. It only looks at the angle.", "compass")
    def card_lean(self, s, candidates, player, rng):
        return RIGHT if s.obs[2] > 0 else LEFT

    @pick("swing", "Follow the swing",
          "Push the way the pole is tipping, judged by its angular velocity.", "timer")
    def card_swing(self, s, candidates, player, rng):
        return RIGHT if s.obs[3] > 0 else LEFT

    @pick("predict", "Look ahead",
          "Add a quarter of the angular velocity to the angle: where will the pole be "
          "in a moment? Push toward that side.", "eye")
    def card_predict(self, s, candidates, player, rng):
        return RIGHT if s.obs[2] + 0.25 * s.obs[3] > 0 else LEFT

    @avoid("stay-on-track", "Stay on the track",
           "Never push the cart further out when it is already past 1.8 units from the "
           "middle.", "barrier")
    def card_stay_on_track(self, s, a: Action, player) -> bool:
        x = s.obs[0]
        return (x > 1.8 and int(a) == RIGHT) or (x < -1.8 and int(a) == LEFT)
