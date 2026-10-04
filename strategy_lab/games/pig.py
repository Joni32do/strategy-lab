"""Pig: push your luck with one die.

The first game every new player meets, so it is short and the odds are exact.
On your turn you roll one die as often as you like. Every roll from 2 to 6
adds to your *turn total*. A 1 ends the turn and the turn total is lost.
*Hold* banks the turn total into your score. First to bank ``target`` points
wins.

Design choices
--------------
* Two chance-free decisions (``"roll"``, ``"hold"``) and one chance node per
  roll, so a turn is a short walk through the game tree: the odds lens can
  show the six outcomes of every roll with their exact probabilities.
* The default target is 50 points, not the classic 100, so a game takes about
  a minute. ``target`` is a parameter (20 to 100).
* ``"hold"`` is also legal before the first roll of a turn. It passes the dice
  and gains nothing. The "Never hold empty" card rules it out. Keeping the
  action always legal keeps the action set the same in every position.

The strategy idea of the game
-----------------------------
A roll adds 4 on average when it does not bust (2..6, equally likely), which
happens with probability 5/6, and loses the turn total ``t`` with probability
1/6. The average change of one more roll is ``(5/6)*4 - t/6 = (20 - t)/6``. It
is positive while ``t`` is under 20: that is the "Hold at 20" card. The better
heuristic "Keep pace" also looks at the score (Neller and Presser solved Pig
exactly in 2004, see the Wikipedia article for the numbers).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, avoid, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.dice import DiceGame, DiceState

ROLL = "roll"
HOLD = "hold"

#: "Keep pace" goes all in once somebody is this close to winning. The published
#: heuristic uses 29 points at target 100. Shorter games scale it down (40% of
#: the target): simulation at target 50 prefers 20 over 29 by about 3.5 points.
MAX_RACE_GAP = 29


@dataclass(kw_only=True)
class PigState(DiceState):
    scores: list[int] = field(default_factory=lambda: [0, 0])
    #: Points collected this turn and not yet banked.
    total: int = 0
    #: The last die rolled (0 before the first roll).
    last: int = 0
    #: The last roll was a 1 and the turn passed.
    busted: bool = False
    #: Points the bust wiped out (for the caption).
    lost: int = 0
    #: Seat that reached the target, or -1.
    won: int = -1


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


class Pig(DiceGame):
    id = "pig"
    name = "Pig"
    icon = "pig"
    tagline = "Roll for points, but a 1 wipes your turn. How greedy can you afford to be?"
    chapter = "chance"
    order = 10
    concepts = ("probability", "independence", "expected-value", "policy", "simulation",
                "law-of-large-numbers", "entropy")
    num_players = 2

    params = {
        "target": Param(50, "Target score",
                        "Bank this many points to win. The classic game plays to 100.",
                        min=20, max=100),
    }

    rulebook = Rulebook(
        summary="Two players race to bank points with one die. On your turn you roll as "
                "often as you like, but a 1 wipes out everything you collected this turn.",
        steps=(
            ("Roll", "Roll the die. A 2, 3, 4, 5 or 6 is added to your turn total. Then you "
                     "choose: roll again or hold."),
            ("Pig out", "Roll a 1 and the turn total is lost. The dice pass to your opponent "
                        "and your banked score does not change."),
            ("Hold", "Hold to add your turn total to your score. Then your opponent plays."),
            ("Win", "The first player to bank the target score wins. The classic game plays "
                    "to 100."),
        ),
        extra=(
            ("Target", "The default target is 50 points so a game takes about a minute. Change "
                       "it between 20 and 100 in the game settings."),
            ("Empty hold", "You may hold before your first roll of a turn. It only passes "
                           "the dice and gains nothing. The classic rules offer hold only "
                           "after a roll."),
        ),
        source="https://en.wikipedia.org/wiki/Pig_(dice_game)",
    )

    models = (
        Model("full", "My score, their score, turn total", True,
              state="(my score, opponent score, turn total at risk)",
              size="about 64,000 positions at the default target of 50 and about 505,000 "
                   "at 100",
              actions="roll or hold",
              transition="roll: with probability 1/6 you bust and lose the turn total, "
                         "otherwise it grows by 2 to 6 with equal chance. Hold: you bank "
                         "the total and the opponent moves, so from your seat the "
                         "opponent is part of the environment.",
              reward="+1 win / -1 loss at the end; gamma = 1",
              note="Exactly the state Neller and Presser solved for the 100 point game. "
                   "The optimal policy is not a single threshold: it holds earlier when "
                   "you lead and rolls on when you trail."),
        Model("no-opponent", "My score and turn total", "approx",
              state="(my score, turn total at risk)",
              size="about 1,300 positions at target 50",
              actions="roll or hold",
              transition="the same dice rules, but the opponent's score is dropped.",
              reward="+1 for reaching the target, 0 otherwise, or the points banked "
                     "per turn",
              note="Your own dynamics stay Markov. What leaks in is the opponent's progress: "
                   "whether 8 points now win the race depends on a number you no longer "
                   "see. Good enough for a fixed threshold, not for the end game."),
        Model("turn-total", "Turn total only", False,
              state="the turn total",
              size="the target (50 positions)",
              actions="roll or hold",
              transition="one more roll adds 2 to 6 or ends the turn.",
              reward="points banked this turn",
              note="Markov for a different goal: 'maximize points per turn'. Its best "
                   "policy is Hold at 20. As a model of winning it is not Markov, because "
                   "the same turn total is worth different things at different scores."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Rolls or holds on a coin flip. Often banks nothing.",
            1, icon="dice"),
        Bot("tim", "Timid Tim", "Holds as soon as he has 10. Safe, slow.", 2,
            cards=("bank-win", "hold10"), icon="shield"),
        Bot("tina", "Twenty Tina", "Holds at 20, the break-even point of one more roll.", 3,
            cards=("bank-win", "hold20"), icon="target"),
        Bot("kai", "Keep-pace Kai", "Holds at 21 plus an eighth of the score gap, and goes "
            "all in when somebody is close to winning.", 4,
            cards=("bank-win", "keep-pace"), icon="chart"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-tim", "Beat Timid Tim", "win", 1, bot="tim"),
        Challenge("odds", "Open the odds lens and look at one roll", "lens", 1, lens="odds"),
        Challenge("beat-tina", "Beat Twenty Tina", "win", 2, bot="tina"),
        Challenge("stack-vs-tina", "Build a card stack that beats Twenty Tina in 55 of 100 "
                  "games", "sim", 3, bot="tina", value=0.55),
    )

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> PigState:
        return PigState()

    def is_terminal(self, s: PigState) -> bool:
        return s.won >= 0

    def winner(self, s: PigState) -> int | None:
        return s.won if s.won >= 0 else None

    def legal_actions(self, s: PigState) -> list[Action]:
        return [ROLL, HOLD]

    def chance_outcomes(self, s: PigState) -> list[tuple[Action, float]]:
        return self.die_outcomes()

    def play(self, s: PigState, a: Action) -> None:
        s.busted = False
        s.lost = 0
        if a == ROLL:
            s.to_move = CHANCE
            return
        s.scores[s.turn] += s.total
        if s.scores[s.turn] >= self.p["target"]:
            s.won = s.turn
            return
        self._pass_dice(s)

    def resolve_chance(self, s: PigState, a: Action) -> None:
        s.last = int(a)
        if s.last == 1:
            s.busted = True
            s.lost = s.total
            self._pass_dice(s)
        else:
            s.total += s.last
            s.to_move = s.turn

    @staticmethod
    def _pass_dice(s: PigState) -> None:
        s.total = 0
        s.turn = 1 - s.turn
        s.to_move = s.turn

    # ------------------------------------------------------------ analysis hooks
    def key(self, s: PigState):
        return (tuple(s.scores), s.turn, s.total, s.to_move, s.won)

    def heuristic(self, s: PigState, player: int) -> float:
        """Lead in points, counting the turn total as half banked."""
        mine = s.scores[player] + (s.total // 2 if s.turn == player else 0)
        theirs = s.scores[1 - player] + (s.total // 2 if s.turn != player else 0)
        return self.squash(mine - theirs, self.p["target"] / 3)

    # --------------------------------------------------------------- rule cards
    def _threshold(self, s: PigState, limit: float) -> Action:
        return HOLD if s.total >= limit else ROLL

    @pick("bank-win", "Bank the win",
          "As soon as holding gets you to the target score, hold.", "trophy")
    def card_bank_win(self, s: PigState, candidates, player, rng):
        if s.scores[player] + s.total >= self.p["target"]:
            return HOLD
        return None

    @pick("hold20", "Hold at 20",
          "Roll until your turn total is 20, then hold. One more roll adds 4 on average "
          "with chance 5/6 and loses your total with chance 1/6, so it pays below 20.",
          "target")
    def card_hold20(self, s: PigState, candidates, player, rng):
        return self._threshold(s, 20)

    @pick("hold10", "Hold at 10",
          "Roll until your turn total is 10, then hold. Safe, but you leave points "
          "on the table.", "shield")
    def card_hold10(self, s: PigState, candidates, player, rng):
        return self._threshold(s, 10)

    @pick("keep-pace", "Keep pace",
          "Hold at 21 plus the score gap divided by 8: trail and you push on, lead and "
          "you bank early. When a player is close to winning, roll until you win.",
          "chart")
    def card_keep_pace(self, s: PigState, candidates, player, rng):
        me, opp = s.scores[player], s.scores[1 - player]
        target = self.p["target"]
        race_gap = min(MAX_RACE_GAP, _round_half_up(0.4 * target))
        if max(me, opp) >= target - race_gap:
            return self._threshold(s, target - me)
        return self._threshold(s, 21 + _round_half_up((opp - me) / 8))

    @avoid("never-hold-empty", "Never hold empty",
           "Do not hold with a turn total of 0: it passes the dice and gains nothing.",
           "barrier")
    def card_never_hold_empty(self, s: PigState, action, player):
        return action == HOLD and s.total == 0

    # ------------------------------------------------------------ presentation
    def move_label(self, s: PigState, a: Action) -> str:
        if a == ROLL:
            return "Roll"
        return f"Hold and bank {s.total}" if s.total else "Hold"

    def describe(self, s: PigState, a: Action, player: int) -> str:
        if a == ROLL:
            return "rolls again" if s.total else "starts rolling"
        if not s.total:
            return "holds with nothing and passes the dice"
        return f"holds and banks {s.total}, now at {s.scores[player] + s.total}"

    def describe_chance(self, s: PigState, a: Action) -> str:
        if a == 1:
            lost = f" and loses {s.total}" if s.total else ""
            return f"rolls a 1{lost}: pig out"
        return f"rolls a {a}: turn total {s.total + a}"

    def status(self, s: PigState, viewer: int | None) -> str:
        if self.is_terminal(s):
            if viewer is None:
                return f"{self.seat_label(s.won)} wins {s.scores[s.won]} to {s.scores[1 - s.won]}"
            word = "You win" if s.won == viewer else "You lose"
            return f"{word}: {s.scores[viewer]} to {s.scores[1 - viewer]}"
        if s.to_move == CHANCE:
            return "The die is rolling"
        note = ""
        if s.busted:
            lost = f" and lost {s.lost}" if s.lost else ""
            note = f"{self.seat_name(1 - s.turn, viewer)} rolled a 1{lost}. "
        if s.turn == viewer:
            if s.total == 0:
                return note + "Your turn: roll the die"
            return f"Roll or hold? Turn total {s.total}"
        who = self.seat_name(s.turn, viewer)
        return note + (f"{who} is deciding (turn total {s.total})" if s.total
                       else f"{who} is about to roll")

    def insight(self, stats: dict) -> str | None:
        n = max(1, stats["n"])
        mine, theirs = stats["wins"][0], stats["wins"][1]
        if mine >= 0.56 * n:
            return (f"You won {mine} of {n}. Hold at 20 banks the most points per turn, but "
                    "winning is a race. Banking early when you lead and pushing on when you "
                    "trail is where a policy that reads the score beats a fixed threshold.")
        if theirs >= 0.56 * n:
            return (f"You lost {theirs} of {n}. One more roll adds 4 on average with chance 5/6 "
                    "and loses your turn total with chance 1/6. Below 20 the average is "
                    "positive, above 20 it is negative. Stacks that hold far from 20 give "
                    "points away.")
        return ("Close. Fixed thresholds near 20 all bank about the same points per turn, so "
                "they win about equally often. Only the score changes the right answer, and "
                "mostly near the end of a game.")

    # ------------------------------------------------------------------ scene
    def _roll_hint(self, s: PigState) -> str:
        if s.total == 0:
            return "Nothing to lose yet. A 1 costs nothing now."
        ev = (20 - s.total) / 6
        return f"1 in 6 to lose {s.total}. Average change {ev:+.1f}."

    def _hold_hint(self, s: PigState) -> str:
        if s.total == 0:
            return "Passes the dice and gains nothing."
        score = s.scores[s.turn]
        if score + s.total >= self.p["target"]:
            return f"Bank {s.total}: {score} -> {score + s.total}. You win."
        return f"Bank {s.total}: {score} -> {score + s.total}."

    def scene(self, s: PigState, viewer: int | None) -> dict:
        target = self.p["target"]
        parts = []
        if s.last:
            roller = self.seat_name(1 - s.turn if s.busted else s.turn, viewer)
            parts.append(self.dice_part([s.last], fresh=s.fresh,
                                        caption=f"{roller} rolled" if s.fresh else "Last roll"))
        bars = []
        for seat in range(2):
            extra = f" + {s.total} in hand" if s.turn == seat and s.total and not self.is_terminal(s) else ""
            bars.append(scene.bar(self.seat_name(seat, viewer), s.scores[seat], max=target,
                                  tone=f"p{seat}", text=f"{s.scores[seat]}{extra}"))
        parts.append(scene.bars(bars, caption=f"First to {target} wins"))
        if not self.is_terminal(s):
            score = s.scores[s.turn]
            parts.append(scene.kv([("Turn total", s.total),
                                   ("If you hold", f"{score} -> {score + s.total}")],
                                  owner=s.turn))
            if s.to_move >= 0 and viewer in (None, s.to_move):
                parts.append(scene.buttons(
                    [(ROLL, self.move_label(s, ROLL)), (HOLD, self.move_label(s, HOLD))],
                    sub=[self._roll_hint(s), self._hold_hint(s)]))
        players = self.scoreboard(s, viewer, score=lambda i: s.scores[i],
                                  sub=lambda i: f"turn total {s.total}" if i == s.turn and s.total else "")
        return scene.scene(parts, players=players, status=self.status(s, viewer))
