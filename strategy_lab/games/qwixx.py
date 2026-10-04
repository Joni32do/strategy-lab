"""Qwixx: a roll-and-write game for two to five players.

The published Gamewright rules (linked in the rulebook), ported from the
lab's earlier Gymnasium environment and turned into a real n-player game.

The sheet
---------
Four color rows. Red and yellow run 2..12 from left to right, green and blue
run 12..2. Crosses in a row must move to the right of your rightmost cross:
numbers you skip are gone for good. A row stores its crosses as a bit mask
(bits 0..10 are the eleven numbers, bit 11 is the lock cross).

A turn
------
The active player rolls six dice (two white, one per color), then two
actions follow in order:

1. **White sum.** Every player may cross the sum of the two white dice in
   one row of their choice. Nobody has to.
2. **Color move.** The active player may add one white die to one colored die
   and cross that sum in the row of that color.

The active player who crossed nothing takes a penalty (-5). Crossing the last
number of a row (12 or 2) needs five crosses in that row first, also crosses
the lock (one more cross) and closes the row for everybody. The game ends the
moment two rows are locked or somebody takes a fourth penalty. A row with
``n`` crosses scores ``n (n + 1) / 2``.

Modelling choices
-----------------
* **Sequential white phase.** The white sum is played by everybody at once.
  Here the seats decide one after another starting with the active player,
  and rows locked in this phase close only when the phase is over. So
  several players can lock the same row on one white sum, exactly as in the
  rules, and the order of decisions changes only what later seats know.
* **Auto-passing.** A seat with no legal cross is skipped, so every decision
  node is a real choice (cross something, or pass).
* **One chance node per die.** Rolling is six small chance nodes (fewer once
  rows are locked and their dice leave the game).
* Seat 0 starts. The rules let the first player to roll a 6 start.
* Returns are win (+1), draw (0) or loss (-1) from the final scores. The
  scores themselves are shown on the scoreboard.

Actions are strings: ``"red:7"`` crosses a 7 in the red row, ``"pass"``
crosses nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, avoid, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.dice import DiceGame, DiceState

ROWS = ("red", "yellow", "green", "blue")
ASCENDING = (True, True, False, False)
NUMBERS = 11                       # columns per row (2..12)
LAST_COL = NUMBERS - 1             # the 12 or 2, which locks the row
LOCK_BIT = 1 << NUMBERS
NUMBER_BITS = LOCK_BIT - 1
LOCK_MIN = 5                       # crosses needed before the lock number
MAX_PENALTIES = 4
PENALTY = 5
LOCKS_TO_END = 2
PASS = "pass"
WHITE_TONES = ("white", "white")


def value_at(row: int, col: int) -> int:
    """The number printed in a cell."""
    return 2 + col if ASCENDING[row] else 12 - col


def col_of(row: int, value: int) -> int:
    """Column of a number in a row, or ``-1`` if the row has no such number."""
    col = value - 2 if ASCENDING[row] else 12 - value
    return col if 0 <= col < NUMBERS else -1


def frontier(mask: int) -> int:
    """Column of the rightmost cross (``-1`` if none)."""
    return (mask & NUMBER_BITS).bit_length() - 1


def triangle(n: int) -> int:
    return n * (n + 1) // 2


def action_name(row: int, value: int) -> str:
    return f"{ROWS[row]}:{value}"


def parse(a: Action) -> tuple[int, int] | None:
    """``"red:7"`` -> ``(0, 7)``; ``"pass"`` -> ``None``."""
    if a == PASS:
        return None
    color, value = str(a).split(":")
    return ROWS.index(color), int(value)


@dataclass(kw_only=True)
class QwixxState(DiceState):
    #: ``marks[seat][row]``: crosses of a row as a bit mask (bit 11 = the lock).
    marks: list[list[int]]
    penalties: list[int]
    #: Rows locked before this roll. They stay open to the white sum of this roll.
    locked: list[bool] = field(default_factory=lambda: [False] * 4)
    #: Rows locked during the white phase; merged into ``locked`` when it ends.
    pending: list[bool] = field(default_factory=lambda: [False] * 4)
    #: White, white, red, yellow, green, blue. 0: not rolled yet, or removed.
    dice: list[int] = field(default_factory=lambda: [0] * 6)
    #: ``"roll"``, ``"white"`` or ``"color"``.
    stage: str = "roll"
    #: Dice rolled so far in this roll.
    rolled: int = 0
    #: White phase: seats that have already had their turn to decide.
    asked: int = 0
    #: The active player has crossed something this turn.
    marked: bool = False
    #: ``(seat, row, value)`` of the latest cross.
    last: tuple[int, int, int] | None = None
    over: bool = False


class Qwixx(DiceGame):
    id = "qwixx"
    name = "Qwixx"
    icon = "sheet"
    tagline = "Everyone crosses every roll. How many numbers will you skip?"
    chapter = "chance"
    order = 30
    concepts = ("distribution-of-sums", "probability", "expected-value", "risk", "policy")
    num_players = 4
    #: A game has up to ~120 chance nodes and ~100 decisions per player in a bad case.
    max_steps = 5000

    params = {
        "players": Param(4, "Players", "How many players share the dice.", min=2, max=5),
    }

    rulebook = Rulebook(
        summary="Everybody marks on every roll, so nobody waits. Each player has a sheet with "
                "a red, yellow, green and blue row. Cross numbers from left to right, score "
                "more points for every further cross in a row, and avoid penalties.",
        steps=(
            ("The sheet", "Red and yellow run 2 to 12 from left to right, green and blue run "
                          "12 down to 2. A cross must be to the right of your rightmost cross "
                          "in that row. Numbers you skip are gone for good."),
            ("The roll", "The active player rolls two white dice and one die per color. "
                         "First every player may cross the sum of the two white dice in one "
                         "row of their choice. Then the active player may add one white die to "
                         "one colored die and cross that sum in the row of that color."),
            ("Penalties", "Nobody is forced to cross. But an active player who crosses nothing "
                          "in both steps takes a penalty worth -5. Other players pass for "
                          "free."),
            ("Locking a row", "To cross the last number of a row (12 for red and yellow, 2 for "
                              "green and blue) you need five crosses in that row. It also "
                              "crosses the lock, which counts as one more cross, and closes the "
                              "row for everyone. Its die leaves the game. Several players can "
                              "lock the same row on the same white sum."),
            ("End and scoring", "The game ends at once when two rows are locked or when "
                                "somebody takes a fourth penalty. A row with n crosses scores "
                                "n(n+1)/2: 1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66, 78. Subtract "
                                "5 per penalty. The highest total wins."),
        ),
        extra=(
            ("One after another", "The white sum is played by all players at once. Here "
                                  "the seats decide one after another, starting with the active "
                                  "player. Rows locked on that sum close only when everybody has "
                                  "decided, so several players can still lock the same row."),
            ("Starting player", "Seat 0 starts. Officially the first player to roll a 6 does."),
            ("Skipped numbers", "On paper you strike skipped numbers with a line yourself. "
                                "The sheet here greys them out for you."),
            ("Scoring", "The scoreboard shows points. For win rates and learning, a game "
                        "counts as a win, a draw or a loss."),
        ),
        source="https://gamewright.com/pdfs/Rules/QwixxTM-RULES.pdf",
    )

    models = (
        Model("counts", "Per-row cross counts and dice", False,
              state="how many crosses you have in each row, your penalties, which rows are "
                    "locked and the six dice",
              size="19 numbers, the most compact encoding that looks honest",
              actions="one cross (row and number) or pass",
              reward="+1 win / -1 loss at the end. The change in your own score each "
                     "step is a denser stand-in.",
              note="The counts are exactly what the score table eats, so this looks "
                   "sufficient, and it is not. Five crosses in red can mean 2 3 4 5 6 (nine "
                   "numbers still open) or 2 3 4 5 11 (only the 12 left). Same count, same "
                   "score so far, completely different legal moves. Everything in Qwixx is "
                   "about the frontier, and a count throws the frontier away."),
        Model("sheet", "Your whole sheet, dice and phase", "approx",
              state="all 44 boxes of your own sheet, your penalties, the locked rows, the six "
                    "dice, whose turn it is and whether this is the white sum or the color move",
              size="59 numbers. One sheet has about 2^44 raw configurations, far fewer "
                   "reachable since crosses only move right.",
              actions="the legal crosses for this roll, or pass",
              reward="+1 / -1 at the end, or the change in your own score",
              note="Markov for your own scoring and for every legality question. It is the "
                   "formulation most human players use. What it cannot see is how close the "
                   "others are: whether the row you are saving is about to be locked out from "
                   "under you, and how many turns are left at all."),
        Model("table", "All sheets, dice and phase", True,
              state="every player's sheet and penalties, the locked rows, the six dice, the "
                    "active seat and the phase",
              size="194 numbers for four players",
              actions="the legal crosses for this roll, or pass",
              reward="+1 win / -1 loss, or your final score minus the best opponent's, which "
                     "is what winning means",
              note="Fully Markov: the dice are rolled fresh every turn, so the sheets plus "
                   "the roll decide everything that can still happen, including when the game "
                   "ends. It also makes the real decision expressible: racing an opponent to "
                   "a lock is a different game from maximising your own sheet."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Crosses or passes on a coin flip. Penalties pile up.",
            1, icon="dice"),
        Bot("gus", "Greedy Gus", "Skips up to three numbers to keep crossing.", 2,
            cards=("lock", "no-fourth", "skip-3", "cheapest"), icon="cherry"),
        Bot("bea", "Bold Bea", "Skips up to two numbers and stacks her best row.", 3,
            cards=("lock", "no-fourth", "skip-2", "best-row", "cheapest"), icon="star"),
        Bot("sam", "Steady Sam", "Skips at most one number for a cross and grabs a lock.", 4,
            cards=("lock", "no-fourth", "skip-1", "cheapest"), icon="scale"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-sam", "Win a game against three Steady Sams", "win", 1, bot="sam"),
        Challenge("model", "Open the model lens and compare the three state spaces", "lens",
                  1, lens="model"),
        Challenge("beat-bea", "Win a game against three Bold Beas", "win", 2, bot="bea"),
        Challenge("stack-vs-sam", "Build a card stack that wins 30 of 100 games against three "
                  "Steady Sams", "sim", 3, bot="sam", value=0.3),
    )

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.num_players = self.p["players"]

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> QwixxState:
        n = self.num_players
        s = QwixxState(marks=[[0] * 4 for _ in range(n)], penalties=[0] * n)
        s.to_move = CHANCE
        return s

    def is_terminal(self, s: QwixxState) -> bool:
        return s.over

    def scores(self, s: QwixxState) -> list[int]:
        return [self.score(s, seat) for seat in range(self.num_players)]

    def row_score(self, mask: int) -> int:
        return triangle(mask.bit_count())

    def score(self, s: QwixxState, seat: int) -> int:
        return (sum(self.row_score(m) for m in s.marks[seat]) - PENALTY * s.penalties[seat])

    def returns(self, s: QwixxState) -> list[float]:
        return self.returns_from_scores(self.scores(s))

    def timeout_returns(self, s: QwixxState) -> list[float]:
        return self.returns_from_scores(self.scores(s))

    def _dice_in_play(self, s: QwixxState) -> list[int]:
        """Indices of the dice rolled this turn, in rolling order."""
        return [0, 1] + [2 + r for r in range(4) if not s.locked[r]]

    def chance_outcomes(self, s: QwixxState) -> list[tuple[Action, float]]:
        return self.die_outcomes()

    # ---- legality
    def can_mark(self, s: QwixxState, seat: int, row: int, col: int, locked: list[bool]) -> bool:
        """May ``seat`` cross column ``col`` of ``row``, given which rows are closed?"""
        if col < 0 or locked[row]:
            return False
        mask = s.marks[seat][row]
        if col <= frontier(mask):
            return False                              # crosses only move right
        if col == LAST_COL and (mask & NUMBER_BITS).bit_count() < LOCK_MIN:
            return False                              # the five-cross rule
        return True

    def white_options(self, s: QwixxState, seat: int) -> list[str]:
        total = s.dice[0] + s.dice[1]
        return [action_name(r, total) for r in range(4)
                if self.can_mark(s, seat, r, col_of(r, total), s.locked)]

    def color_options(self, s: QwixxState, seat: int) -> list[str]:
        out: list[str] = []
        for r in range(4):
            if s.locked[r]:
                continue                              # that die has left the game
            for white in sorted({s.dice[0], s.dice[1]}):
                value = white + s.dice[2 + r]
                name = action_name(r, value)
                if name not in out and self.can_mark(s, seat, r, col_of(r, value), s.locked):
                    out.append(name)
        return out

    def legal_actions(self, s: QwixxState) -> list[Action]:
        if s.stage == "white":
            return self.white_options(s, s.to_move) + [PASS]
        return self.color_options(s, s.turn) + [PASS]

    # ---- flow
    def resolve_chance(self, s: QwixxState, a: Action) -> None:
        order = self._dice_in_play(s)
        s.dice[order[s.rolled]] = int(a)
        s.rolled += 1
        if s.rolled == len(order):
            s.stage = "white"
            s.asked = 0
            self._ask_next_white(s)

    def play(self, s: QwixxState, a: Action) -> None:
        seat = s.to_move
        cross = parse(a)
        if s.stage == "white":
            if cross is not None:
                self._cross(s, seat, *cross)
                if col_of(*cross) == LAST_COL:
                    s.pending[cross[0]] = True        # closes when the white phase ends
            s.asked += 1
            self._ask_next_white(s)
        else:                                          # the active player's color move
            if cross is not None:
                self._cross(s, seat, *cross)
                if col_of(*cross) == LAST_COL:
                    s.locked[cross[0]] = True
            self._end_turn(s)

    def _cross(self, s: QwixxState, seat: int, row: int, value: int) -> None:
        col = col_of(row, value)
        s.marks[seat][row] |= 1 << col
        if col == LAST_COL:
            s.marks[seat][row] |= LOCK_BIT              # the lock counts as one more cross
        s.last = (seat, row, value)
        if seat == s.turn:
            s.marked = True

    def _ask_next_white(self, s: QwixxState) -> None:
        n = self.num_players
        while s.asked < n:
            seat = (s.turn + s.asked) % n
            if self.white_options(s, seat):
                s.to_move = seat
                return
            s.asked += 1
        self._end_white(s)

    def _end_white(self, s: QwixxState) -> None:
        for r in range(4):
            if s.pending[r]:
                s.locked[r] = True
                s.pending[r] = False
        if sum(s.locked) >= LOCKS_TO_END:
            s.over = True                               # ends at once, no color move
            return
        s.stage = "color"
        if self.color_options(s, s.turn):
            s.to_move = s.turn
        else:
            self._end_turn(s)

    def _end_turn(self, s: QwixxState) -> None:
        if not s.marked:
            s.penalties[s.turn] += 1
        if sum(s.locked) >= LOCKS_TO_END or max(s.penalties) >= MAX_PENALTIES:
            s.over = True
            return
        s.turn = (s.turn + 1) % self.num_players
        s.to_move = CHANCE
        s.stage = "roll"
        s.dice = [0] * 6
        s.rolled = 0
        s.marked = False

    # ------------------------------------------------------------ analysis hooks
    def key(self, s: QwixxState):
        return (tuple(tuple(m) for m in s.marks), tuple(s.penalties), tuple(s.locked),
                tuple(s.pending), tuple(s.dice), s.stage, s.rolled, s.asked, s.marked,
                s.turn, s.to_move, s.over)

    def heuristic(self, s: QwixxState, player: int) -> float:
        scores = self.scores(s)
        rest = [v for i, v in enumerate(scores) if i != player]
        return self.squash(scores[player] - max(rest), 15)

    # --------------------------------------------------------------- rule cards
    def cost(self, s: QwixxState, seat: int, action: Action) -> int:
        """How many numbers crossing ``action`` skips in its row."""
        row, value = parse(action)
        return col_of(row, value) - frontier(s.marks[seat][row]) - 1

    def _crosses(self, candidates) -> list[str]:
        return [a for a in candidates if a != PASS]

    def _penalty_looms(self, s: QwixxState, seat: int) -> bool:
        """Would passing now cost the active player a penalty?"""
        return s.stage == "color" and seat == s.turn and not s.marked

    @pick("lock", "Grab the lock",
          "If you can cross a 12 or 2 and lock the row, do it. The lock is one more cross.",
          "shield")
    def card_lock(self, s: QwixxState, candidates, player, rng):
        locks = [a for a in self._crosses(candidates)
                 if col_of(*parse(a)) == LAST_COL]
        return min(locks, key=lambda a: self.cost(s, player, a)) if locks else None

    @avoid("no-fourth", "Dodge the fourth penalty",
           "Never pass when that would be your own fourth penalty and a cross is possible.",
           "barrier")
    def card_no_fourth(self, s: QwixxState, action, player):
        return (action == PASS and self._penalty_looms(s, player)
                and s.penalties[player] == MAX_PENALTIES - 1)

    def _skip_card(limit: int):                       # noqa: N805 - builds class attributes
        def veto(self, s: QwixxState, action, player):
            if action == PASS:
                return False
            bar = limit + (2 if self._penalty_looms(s, player) else 0)
            return self.cost(s, player, action) > bar
        return avoid(f"skip-{limit}", "Never skip" if limit == 0 else f"Skip at most {limit}",
                     ("Cross only the very next number in a row." if limit == 0 else
                      f"Pass on crosses that skip more than {limit} number"
                      f"{'' if limit == 1 else 's'}.")
                     + " The bar rises by 2 when passing would cost a penalty.",
                     "ladder")(veto)

    card_skip0 = _skip_card(0)
    card_skip1 = _skip_card(1)
    card_skip2 = _skip_card(2)
    card_skip3 = _skip_card(3)
    del _skip_card

    @pick("cheapest", "Cheapest cross",
          "Take the cross that skips the fewest numbers. Ties go to the row with more crosses.",
          "coin")
    def card_cheapest(self, s: QwixxState, candidates, player, rng):
        crosses = self._crosses(candidates)
        if not crosses:
            return None

        def rank(a):
            row, _ = parse(a)
            return (self.cost(s, player, a), -s.marks[player][row].bit_count(), row)
        return min(crosses, key=rank)

    @pick("best-row", "Feed your best row",
          "Cross in the row where you already have the most crosses. Each cross there is "
          "worth one point more than the last.", "chart")
    def card_best_row(self, s: QwixxState, candidates, player, rng):
        crosses = self._crosses(candidates)
        if not crosses:
            return None
        return max(crosses, key=lambda a: (s.marks[player][parse(a)[0]].bit_count(),
                                           -self.cost(s, player, a)))

    # ------------------------------------------------------------ presentation
    def move_label(self, s: QwixxState, a: Action) -> str:
        parsed = parse(a)
        if parsed is None:
            return "Pass (penalty)" if self._penalty_looms(s, s.to_move) else "Pass"
        row, value = parsed
        verb = "Lock" if col_of(row, value) == LAST_COL else "Cross"
        return f"{verb} {ROWS[row]} {value}"

    def outcome_label(self, s: QwixxState, a: Action) -> str:
        return str(a)

    def describe(self, s: QwixxState, a: Action, player: int) -> str:
        parsed = parse(a)
        if parsed is None:
            if self._penalty_looms(s, player):
                return "passes and takes a penalty (-5)"
            return "passes"
        row, value = parsed
        skipped = self.cost(s, player, a)
        text = f"crosses {ROWS[row]} {value}"
        if col_of(row, value) == LAST_COL:
            text += " and locks the row"
        if skipped > 0:
            text += f", skipping {skipped}"
        return text

    def describe_chance(self, s: QwixxState, a: Action) -> str:
        die = self._dice_in_play(s)[s.rolled]
        which = "a white die" if die < 2 else f"the {ROWS[die - 2]} die"
        return f"rolls {a} on {which}"

    def status(self, s: QwixxState, viewer: int | None) -> str:
        if self.is_terminal(s):
            scores = self.scores(s)
            best = max(scores)
            if viewer is None:
                return "Game over: " + ", ".join(f"{self.seat_label(i)} {v}"
                                                 for i, v in enumerate(scores))
            if scores[viewer] == best:
                word = "You win" if scores.count(best) == 1 else "You share the win"
            else:
                word = "You lose"
            return f"{word}: {scores[viewer]} points, best {best}"
        if s.to_move == CHANCE:
            return "The dice are rolling"
        who = self.seat_name(s.to_move, viewer)
        if s.stage == "white":
            total = s.dice[0] + s.dice[1]
            if s.to_move == viewer:
                extra = " Then you get a color move." if s.turn == viewer else ""
                return f"White sum {total}: cross it in one row, or pass.{extra}"
            return f"White sum {total}. {who} is deciding"
        if s.to_move == viewer:
            warn = "" if s.marked else " Passing costs a penalty."
            return f"Color move: one white die plus one colored die, or pass.{warn}"
        return f"{who} is choosing a color move"

    def insight(self, stats: dict) -> str | None:
        n = max(1, stats["n"])
        mine = stats["wins"][0]
        share = mine / n
        fair = 1 / self.num_players
        if share >= fair + 0.15:
            return (f"You won {mine} of {n}, well above a fair share of {fair:.0%}. A cross is "
                    "worth one more point than the last in its row, so stacking one row and "
                    "skipping little beats scattering crosses. The triangular score rewards "
                    "patience until a lock ends the game.")
        if share <= fair - 0.1:
            return (f"You won {mine} of {n}, under a fair share of {fair:.0%}. Skipping many "
                    "numbers spends crosses you can never get back, and every pass by the "
                    "active player costs 5 points. Compare how many numbers your stack "
                    "skips with the bot's.")
        return ("Close to a fair share. Skip tolerance is a trade: skip a lot and you cross "
                "often but run out of numbers, skip nothing and you cross too rarely. The best "
                "level sits in between.")

    # ------------------------------------------------------------------ scene
    def _sheet(self, s: QwixxState, seat: int, viewer: int | None, *, live: set[str],
               compact: bool) -> dict:
        rows = []
        mine = s.marks[seat]
        for r in range(4):
            mask = mine[r]
            edge = frontier(mask)
            cells = []
            for col in range(NUMBERS):
                value = value_at(r, col)
                name = action_name(r, value)
                crossed = bool((mask >> col) & 1)
                cell = scene.sheet_cell(str(value), crossed=crossed,
                                        action=name if name in live else None)
                if not crossed and (col <= edge or s.locked[r]):
                    cell["tone"] = "muted"            # skipped or closed: out of reach
                cells.append(cell)
            cells.append(scene.sheet_cell("lock", crossed=bool(mask & LOCK_BIT), lock=True))
            rows.append(scene.sheet_row(ROWS[r], cells, locked=s.locked[r] or s.pending[r],
                                        score=self.row_score(mask)))
        penalty_click = PASS if PASS in live and self._penalty_looms(s, seat) else None
        return scene.sheet("Your sheet" if seat == viewer else self.seat_label(seat), rows,
                           owner=seat, penalties=s.penalties[seat],
                           penalty_action=penalty_click, score=self.score(s, seat),
                           active=seat == s.turn and not s.over, compact=compact)

    def scene(self, s: QwixxState, viewer: int | None) -> dict:
        parts = []
        order = self._dice_in_play(s)
        shown = [i for i in order if s.dice[i]]
        if shown:
            tones = [("white", "white", *ROWS)[i] for i in shown]
            both = s.dice[0] and s.dice[1]
            caption = f"White sum {s.dice[0] + s.dice[1]}" if both else ""
            parts.append(self.dice_part([s.dice[i] for i in shown], tones=tones,
                                        fresh=s.fresh, caption=caption))
        me = viewer if viewer is not None else (s.to_move if s.to_move >= 0 else s.turn)
        live: set[str] = set()
        if not s.over and s.to_move >= 0 and viewer in (None, s.to_move):
            live = set(self.legal_actions(s))
        parts.append(self._sheet(s, me, viewer, live=live if me == s.to_move else set(),
                                 compact=False))
        for seat in range(self.num_players):
            if seat != me:
                parts.append(self._sheet(s, seat, viewer, live=set(), compact=True))

        def sub(i: int) -> str:
            rows = " ".join(f"{ROWS[r][0].upper()}{s.marks[i][r].bit_count()}" for r in range(4))
            pen = s.penalties[i]
            return f"{rows}, {pen} penalt{'y' if pen == 1 else 'ies'}"

        players = self.scoreboard(s, viewer, score=lambda i: self.score(s, i), sub=sub)
        return scene.scene(parts, players=players, status=self.status(s, viewer))
