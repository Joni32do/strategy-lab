"""Snakes & Ladders, the "lucky picks" variant.

Plain Snakes & Ladders has no decisions, so there is nothing to learn from
playing it. Here you roll **two dice and keep one**: each turn a chance node
rolls the unordered pair (21 outcomes) and you choose which die to move by.
You race from the start to square 100 and must land on it exactly. A die that
would carry you past 100 bounces you back (``bounce``, on by default).

The board is the classic 10 by 10 layout with 9 ladders and 10 snakes.
Squares are numbered in a serpentine, square 1 at the bottom left, so the grid
scene draws ``JUMPS`` as arrows between cells.

What there is to learn: a choice every turn compounds. Always taking the die
with the best final square (the "Far sighted" card) beats a random picker in
about 86 of 100 games (2000 simulated games). Two sensible policies, however,
land close to a coin flip: Lucky Lena beats Cautious Cleo only 53 to 47. Where
the skill ceiling sits is the lesson of the game, and the simulation shows it.

Actions are die values (``1..6``). A double offers one action only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, pick, avoid, scene
from strategy_lab.core.game import Action
from strategy_lab.families.dice import DiceState, RollAndMoveGame

#: Ladders go up (destination above the key), snakes down. The classic layout.
JUMPS: dict[int, int] = {
    1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100,
    16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78,
}
LAST = 100


def square_index(n: int) -> int:
    """Row-major cell index of square ``n`` (1..100) in the 10 by 10 grid."""
    row_from_bottom, c = divmod(n - 1, 10)
    col = c if row_from_bottom % 2 == 0 else 9 - c
    return (9 - row_from_bottom) * 10 + col


@dataclass(kw_only=True)
class SnakesState(DiceState):
    #: Square of each token (0 = before the board).
    pos: list[int] = field(default_factory=lambda: [0, 0])
    #: The pair rolled this turn, smaller die first ((0, 0) before the first roll).
    dice: tuple[int, int] = (0, 0)
    #: ``(seat, square landed on, final square)`` of the latest move, or ``None``.
    last: tuple[int, int, int] | None = None
    won: int = -1


class SnakesAndLadders(RollAndMoveGame):
    id = "snakes"
    name = "Snakes & Ladders"
    icon = "snake"
    tagline = "Roll two dice, keep one. How much can strategy beat luck?"
    chapter = "chance"
    order = 20
    concepts = ("probability", "independence", "expected-value", "policy", "simulation",
                "luck-vs-skill")
    num_players = 2
    max_steps = 1200

    params = {
        "bounce": Param(True, "Bounce at 100",
                        "An overshoot counts backwards from 100. Off: an overshoot "
                        "leaves you where you are."),
    }

    rulebook = Rulebook(
        summary="Race your token from the start to square 100. Each turn you roll two dice "
                "and move by one of them. Ladders lift you, snakes drop you.",
        steps=(
            ("Roll two dice", "Both dice are rolled for you. Choose one of them and move "
                              "that many squares. On a double there is nothing to choose."),
            ("Ladders and snakes", "Land on the foot of a ladder and you climb to its top. "
                                   "Land on a snake's head and you slide down to its tail."),
            ("Exact finish", "Land exactly on square 100 to win. A die that would take you "
                             "past 100 bounces you back: the extra steps count backwards "
                             "from 100."),
        ),
        extra=(
            ("Lucky picks", "Classic Snakes and Ladders has no choices: you move by what the "
                            "dice say. Keeping one of two dice is this lab's own variant, so "
                            "that a strategy has something to decide."),
            ("Bounce", "The bounce at 100 is a game setting. Switch it off and a die that "
                       "overshoots 100 leaves your token where it is."),
            ("Board", "The classic layout: 9 ladders and 10 snakes on a 10 by 10 board. "
                      "There is no single official layout."),
        ),
    )

    models = (
        Model("full", "My square, their square, the two dice", True,
              state="(my square, opponent square, the pair just rolled)",
              size="101 x 101 x 21 = about 214,000 positions",
              actions="the die to move by (1 or 2 choices)",
              transition="the move is deterministic once you pick a die, then the "
                         "opponent rolls and moves: from your seat the opponent is part "
                         "of the environment.",
              reward="+1 win / -1 loss at the end; gamma = 1",
              note="The honest model of the race. Tokens never interact, so the opponent "
                   "only matters as a clock."),
        Model("solo", "My square and the two dice", "approx",
              state="(my square, the pair just rolled)",
              size="101 x 21 = 2,121 positions",
              actions="the die to move by",
              transition="the same, without the opponent.",
              reward="-1 per turn until you finish (minimize the number of turns)",
              note="Markov for your own progress, and small enough to solve exactly by "
                   "value iteration. It ignores who is ahead, so it cannot tell when a "
                   "risky die is worth it. The lab's 'Far sighted' card is the greedy "
                   "version of its answer."),
        Model("square", "My square only", False,
              state="my square",
              size="101 positions",
              actions="none you can list: the legal dice are unknown before the roll",
              transition="roll, choose, move.",
              reward="-1 per turn",
              note="Looks like the state because it is all the board shows, but the "
                   "decision depends on the two dice. Without them the legal actions do "
                   "not exist, so this is not Markov for the decision problem."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Picks a die at random. Pure chaos.", 1, icon="dice"),
        Bot("harry", "Hasty Harry", "Always takes the bigger die. Snakes? What snakes?", 2,
            cards=("big",), icon="race"),
        Bot("cleo", "Cautious Cleo", "Dodges snakes, climbs ladders, then floors it.", 3,
            cards=("dodge", "ladder", "big"), icon="shield"),
        Bot("lena", "Lucky Lena", "Plays the percentages on every single roll.", 4,
            cards=("sniper", "dodge", "no-bounce", "ladder", "far"), icon="star"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-harry", "Beat Hasty Harry", "win", 1, bot="harry"),
        Challenge("odds", "Open the odds lens and look at one roll", "lens", 1, lens="odds"),
        Challenge("beat-lena", "Beat Lucky Lena", "win", 2, bot="lena"),
        Challenge("stack-vs-harry", "Build a card stack that beats Hasty Harry in 75 of 100 "
                  "games", "sim", 3, bot="harry", value=0.75),
    )

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> SnakesState:
        return SnakesState(to_move=CHANCE)

    def is_terminal(self, s: SnakesState) -> bool:
        return s.won >= 0

    def winner(self, s: SnakesState) -> int | None:
        return s.won if s.won >= 0 else None

    def legal_actions(self, s: SnakesState) -> list[Action]:
        return sorted(set(s.dice))

    def chance_outcomes(self, s: SnakesState) -> list[tuple[Action, float]]:
        return self.pair_outcomes()

    def landing(self, pos: int, die: int) -> tuple[int, int]:
        """Where ``die`` takes a token on ``pos``.

        Returns ``(square landed on, square after the snake or ladder)``. An
        overshoot without ``bounce`` leaves the token where it is.
        """
        if pos + die > LAST and not self.p["bounce"]:
            return pos, pos
        raw = self.advance(pos, die, LAST, "bounce").dest
        return raw, JUMPS.get(raw, raw)

    def resolve_chance(self, s: SnakesState, a: Action) -> None:
        s.dice = self.parse_pair(a)
        s.to_move = s.turn

    def play(self, s: SnakesState, a: Action) -> None:
        seat = s.turn
        raw, final = self.landing(s.pos[seat], int(a))
        s.pos[seat] = final
        s.last = (seat, raw, final)
        if final == LAST:
            s.won = seat
            return
        s.turn = 1 - seat
        s.to_move = CHANCE

    # ------------------------------------------------------------ analysis hooks
    def key(self, s: SnakesState):
        return (tuple(s.pos), s.turn, s.to_move, s.dice, s.won)

    def standing(self, s: SnakesState, seat: int) -> float:
        return s.pos[seat]

    def heuristic(self, s: SnakesState, player: int) -> float:
        return self.squash(s.pos[player] - s.pos[1 - player], 25)

    # --------------------------------------------------------------- rule cards
    def _is_ladder_foot(self, square: int) -> bool:
        return square in JUMPS and JUMPS[square] > square

    def _is_snake_head(self, square: int) -> bool:
        return square in JUMPS and JUMPS[square] < square

    @pick("sniper", "Photo finish",
          "If one die lands you exactly on square 100, take it. Game over.", "flag")
    def card_sniper(self, s: SnakesState, candidates, player, rng):
        pos = s.pos[player]
        return next((a for a in candidates if self.landing(pos, a)[1] == LAST), None)

    @pick("ladder", "Ladder lover",
          "Prefer a die that lands on the foot of a ladder. Of several, climb the highest.",
          "ladder")
    def card_ladder(self, s: SnakesState, candidates, player, rng):
        pos = s.pos[player]
        ups = [a for a in candidates if self._is_ladder_foot(self.landing(pos, a)[0])]
        if not ups:
            return None
        return max(ups, key=lambda a: self.landing(pos, a)[1])

    @avoid("dodge", "Snake dodger",
           "Veto dice that drop you on a snake's head, when you have a choice.", "snake")
    def card_dodge(self, s: SnakesState, action, player):
        return self._is_snake_head(self.landing(s.pos[player], action)[0])

    @avoid("no-bounce", "No overshoot",
           "Avoid shooting past square 100 and bouncing backwards.", "barrier")
    def card_no_bounce(self, s: SnakesState, action, player):
        return s.pos[player] + action > LAST

    @pick("far", "Far sighted",
          "Take the die with the best final square, counting snakes, ladders and bounces.",
          "eye")
    def card_far(self, s: SnakesState, candidates, player, rng):
        pos = s.pos[player]
        return max(candidates, key=lambda a: self.landing(pos, a)[1])

    @pick("big", "Full throttle", "Always take the bigger die. Raw speed, no questions.",
          "race")
    def card_big(self, s: SnakesState, candidates, player, rng):
        return max(candidates)

    @pick("small", "Baby steps", "Always take the smaller die. Bold theory. Test it!",
          "footprints")
    def card_small(self, s: SnakesState, candidates, player, rng):
        return min(candidates)

    # ------------------------------------------------------------ presentation
    def move_label(self, s: SnakesState, a: Action) -> str:
        return f"Move {a}"

    def describe(self, s: SnakesState, a: Action, player: int) -> str:
        pos, die = s.pos[player], int(a)
        raw, final = self.landing(pos, die)
        overshoot = pos + die > LAST
        text = f"takes the {die}"
        if overshoot and not self.p["bounce"]:
            return f"{text} but overshoots 100 and stays on {pos}"
        if overshoot:
            text += f", bounces off 100 and lands on {raw}"
        else:
            text += f" from {'the start' if pos == 0 else pos} to {raw}"
        if final > raw:
            text += f", climbs the ladder to {final}"
        elif final < raw:
            text += f", slides down the snake to {final}"
        if final == LAST:
            text += ", and wins"
        return text

    def status(self, s: SnakesState, viewer: int | None) -> str:
        if self.is_terminal(s):
            if viewer is None:
                return f"{self.seat_label(s.won)} reaches 100 and wins"
            return "You reach 100 and win" if s.won == viewer else "The opponent reaches 100"
        if s.to_move == CHANCE:
            return "The dice are rolling"
        a, b = s.dice
        who = self.seat_name(s.turn, viewer)
        if s.turn == viewer:
            return f"Double {a}: move {a}" if a == b else f"You rolled {a} and {b}: pick a die"
        return f"{who} rolled {a} and {b} and is choosing"

    def insight(self, stats: dict) -> str | None:
        n = max(1, stats["n"])
        a, b = stats["wins"][0], stats["wins"][1]
        if abs(a - b) <= 0.12 * n:
            return ("Dead even. Once both sides pick their dice halfway sensibly, the rest is "
                    "pure dice. There is no fork or checkmate hiding in Snakes & Ladders, so "
                    "two decent policies converge to a coin flip. Knowing where the skill "
                    "ceiling of a game sits is a strategy insight too. Compare this with "
                    "Tic-Tac-Toe.")
        if a > b:
            return (f"A real edge: {a} to {b}. Every turn you choose between two squares, so "
                    "small gains pile up: ladders taken, snakes dodged, no wasted overshoots. "
                    f"Over {n} games that adds up to a clear lead.")
        return (f"The bot won {b} to {a}. It picks better dice than your stack. The strongest "
                "single idea is Far sighted: look at the final square after snakes, "
                "ladders and bounces. Try it first.")

    # ------------------------------------------------------------------ scene
    def _board(self, s: SnakesState) -> dict:
        here: dict[int, list[int]] = {}
        for seat, square in enumerate(s.pos):
            if square > 0:
                here.setdefault(square, []).append(seat)
        landed = s.last[2] if s.last else -1
        cells: list[dict | None] = [None] * 100
        for n in range(1, LAST + 1):
            tone = ""
            icon = badge = ""
            if self._is_ladder_foot(n):
                tone, icon, badge = "ladder", "ladder", f"^{JUMPS[n]}"
            elif self._is_snake_head(n):
                tone, icon, badge = "snake", "snake", f"v{JUMPS[n]}"
            if n == LAST:
                tone = "goal"
            if n == landed:
                tone = "last"
            cells[square_index(n)] = scene.cell(
                pieces=[scene.piece(seat, "token") for seat in here.get(n, ())],
                tone=tone, label=str(n), icon=icon, badge=badge)
        links = [scene.link(square_index(a), square_index(b), "up" if b > a else "down")
                 for a, b in JUMPS.items()]
        return scene.grid(10, 10, cells, style="tiles", links=links)

    def scene(self, s: SnakesState, viewer: int | None) -> dict:
        parts = [self._board(s)]
        if s.dice[0]:
            decision = not self.is_terminal(s) and s.to_move >= 0 and viewer in (None, s.to_move)
            roller = self.seat_name(s.turn, viewer)
            parts.append(self.dice_part(
                s.dice, fresh=s.fresh,
                actions=list(s.dice) if decision else None,
                caption=f"{roller} rolled" if s.fresh else "Last roll"))
        players = self.scoreboard(
            s, viewer,
            score=lambda i: "start" if s.pos[i] == 0 else f"square {s.pos[i]}",
            sub=lambda i: f"{LAST - s.pos[i]} to go")
        return scene.scene(parts, players=players, status=self.status(s, viewer))
