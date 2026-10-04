"""Mensch aergere dich nicht (Ludo): race four tokens home and kick the others back.

The classic German family game on the cross-shaped board of 40 ring squares.
Each player has four tokens, a base in a corner, a start square on the ring
and four home cells in front of the start square.

Rules as played here
--------------------
* All four tokens start in the base. Only a 6 brings a token out, onto your
  start square (an opponent standing there is captured). A 6 also gives
  another roll.
* One token moves per roll, clockwise, by the number rolled. Tokens may jump
  over others. You may not land on your own token.
* Landing on an opponent's token sends it back to its base.
* After a full lap a token turns into the home cells. Tokens may move on
  inside the home cells (jumping is allowed there), the exact roll is needed
  to stop on a free cell. The first player with all four tokens home wins.
* With no legal move the turn passes. With ``players`` 2 or 3 the seats
  take the colors in order (two players sit opposite each other).

This is the lab's long-standing version of the rules (it came from the
original JavaScript game) and follows the Schmidt Spiele rules, linked in the
rulebook, with these differences. Each can be switched to the official
behavior with a setting, and all of them are listed in the rulebook:

* The official game starts with one token already on the start square
  (``start_token``).
* The official game forces you to bring a token out on a 6 and to clear the
  start square as soon as you can (``forced_entry``). Here entering is a choice,
  which is what gives the "Fresh legs" card something to decide.
* Three tries to roll a 6 when no token is on the track (``three_tries``) and
  forced capturing (``must_capture``) are official *variants*. Both are off.
* The official game lets 2 players use two colors each. Here every player has
  one color and four tokens.
* The player who rolls first is seat 0, not the highest roll.

Tokens of one player are interchangeable, so a state stores each player's
four positions sorted, and an action names the *position* of the token to move
(``-1`` brings one out of the base). A position is the token's progress from
its own start: ``-1`` base, ``0..39`` ring squares, ``40..43`` home cells.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, avoid, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.dice import DiceState, RollAndMoveGame

RING = 40                    # squares on the ring
HOME_FIRST = 40              # progress of the first home cell
LAST_PROGRESS = 43           # progress of the last home cell
BASE = -1
ENTER = -1                   # the action "bring a token out of the base"
#: Ring index of the start square of each of the four arms.
ARM_START = (0, 10, 20, 30)
#: Which arms the seats use. Two players sit opposite each other.
SEAT_ARMS = {2: (0, 2), 3: (0, 1, 2), 4: (0, 1, 2, 3)}

# ---- board geometry on the 11 x 11 grid (row, col) -------------------------
#: The 40 ring squares clockwise, starting at the start square of arm 0.
RING_CELLS = (
    (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (3, 4), (2, 4), (1, 4), (0, 4), (0, 5),
    (0, 6), (1, 6), (2, 6), (3, 6), (4, 6), (4, 7), (4, 8), (4, 9), (4, 10), (5, 10),
    (6, 10), (6, 9), (6, 8), (6, 7), (6, 6), (7, 6), (8, 6), (9, 6), (10, 6), (10, 5),
    (10, 4), (9, 4), (8, 4), (7, 4), (6, 4), (6, 3), (6, 2), (6, 1), (6, 0), (5, 0),
)
HOME_CELLS = (
    ((5, 1), (5, 2), (5, 3), (5, 4)),
    ((1, 5), (2, 5), (3, 5), (4, 5)),
    ((5, 9), (5, 8), (5, 7), (5, 6)),
    ((9, 5), (8, 5), (7, 5), (6, 5)),
)
BASE_CELLS = (
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((0, 9), (0, 10), (1, 9), (1, 10)),
    ((9, 9), (9, 10), (10, 9), (10, 10)),
    ((9, 0), (9, 1), (10, 0), (10, 1)),
)


@dataclass(kw_only=True)
class MaednState(DiceState):
    #: Per seat the four token positions, sorted (see the module docstring).
    tokens: list[list[int]]
    #: The die to play (0 before the first roll).
    die: int = 0
    #: Rolls left this turn (three tries for a 6 in the variant, else 1).
    tries: int = 1
    #: ``(seat, destination)`` of the latest move, or ``None``.
    last: tuple[int, int] | None = None
    won: int = -1


def _grid_index(cell: tuple[int, int]) -> int:
    return cell[0] * 11 + cell[1]


@lru_cache(maxsize=None)
def _template(players: int) -> tuple[dict | None, ...]:
    """The empty board as 121 cell dicts (``None`` off the board), built once."""
    cells: list[dict | None] = [None] * 121
    used = SEAT_ARMS[players]
    for cell in RING_CELLS:
        cells[_grid_index(cell)] = scene.cell()
    for seat, arm in enumerate(used):
        cells[_grid_index(RING_CELLS[ARM_START[arm]])] = scene.cell(tone=f"p{seat}", icon="flag")
    for arm in range(4):
        tone = f"p{used.index(arm)}" if arm in used else "muted"
        for h, cell in enumerate(HOME_CELLS[arm]):
            cells[_grid_index(cell)] = scene.cell(tone=tone, label=str(h + 1))
        for cell in BASE_CELLS[arm]:
            cells[_grid_index(cell)] = scene.cell(tone=tone)
    return tuple(cells)


class Maedn(RollAndMoveGame):
    id = "maedn"
    name = "Mensch \xe4rgere dich nicht"
    icon = "pawn"
    tagline = "Race four tokens home and kick your opponents back to base."
    chapter = "dice-and-choice"
    order = 10
    concepts = ("probability", "expected-value", "policy", "risk", "luck-vs-skill", "simulation")
    num_players = 4
    #: Random playouts of four players are long; the cap only matters for stuck games.
    max_steps = 8000

    params = {
        "players": Param(4, "Players", "How many players share the board.", min=2, max=4),
        "three_tries": Param(False, "Three tries for a 6",
                             "With no token on the track you roll up to three times to get "
                             "a 6 (official variant)."),
        "must_capture": Param(False, "Must capture",
                              "If a move captures an opponent's token you have to make it "
                              "(official variant)."),
        "forced_entry": Param(False, "Forced entry",
                              "A 6 must bring a new token out and the start square must be "
                              "cleared first (official base rule)."),
        "start_token": Param(False, "One token starts out",
                             "Every player begins with one token on the start square "
                             "(official base rule)."),
    }

    rulebook = Rulebook(
        summary="Race four tokens around the board and into your home cells. Landing on an "
                "opponent's token sends it back to its base.",
        steps=(
            ("Getting out", "All tokens wait in your base. Only a 6 brings one out, onto "
                            "your start square. A 6 also gives you another roll."),
            ("Moving", "Each turn you roll once and move one token clockwise by the number "
                       "rolled. You may jump over other tokens but never land on your own."),
            ("Capturing", "Land on an opponent's token and it goes back to its base. It "
                          "needs a new 6 to return."),
            ("Home", "After one lap your token turns into the four home cells in front of "
                     "your start square. Only the right number lets it stop on a free cell. "
                     "Tokens may jump over each other in the home cells."),
            ("Winning", "The first player with all four tokens in the home cells wins."),
        ),
        extra=(
            ("Starting position", "The official game starts with one token already on the "
                                  "start square. Here all four wait in the base, unless you "
                                  "switch on 'One token starts out'."),
            ("Entering", "Officially a 6 must bring a new token out and the start square must "
                         "be cleared as soon as possible. Here entering is your choice, unless "
                         "you switch on 'Forced entry'."),
            ("Variants", "'Three tries for a 6' and 'Must capture' are official variants of "
                         "the Schmidt Spiele rules and are off by default."),
            ("Players", "Official 2 or 3 player games give each player two or more colors. "
                        "Here each player has one color and four tokens, and the first seat "
                        "starts instead of the highest roll."),
        ),
        source="https://www.schmidtspiele.de/files/Produkte/4/49020%20-%20Standardausgabe/"
               "49020_49021_Mensch_aergere_Dich_nicht_DE.pdf",
    )

    models = (
        Model("board", "All tokens, the die and whose turn", True,
              state="the position of all 16 tokens (base, ring square or home cell), the "
                    "die just rolled and the seat to move",
              size="about 10^18 positions for four players",
              actions="bring a token out, or move one of up to 4 tokens",
              transition="the die is fresh every turn, so the position plus the die "
                         "decides everything. Captures send tokens to base.",
              reward="+1 for being first home, -1 otherwise; gamma = 1",
              note="Honest and huge. Tokens of one player are interchangeable, which "
                   "already cuts the table by a factor of up to 24 per player."),
        Model("danger", "My progress plus danger features", "approx",
              state="my four token positions, how many enemy tokens sit 1 to 6 squares "
                    "behind each of mine, how many I could capture, the die",
              size="about 10^8 positions",
              actions="the same moves",
              transition="the enemy's exact squares are summarized as counts.",
              reward="+1 / -1 at the end",
              note="Captures are the whole drama, and they depend on where enemies are "
                   "right now. A count of enemies in reach keeps that and drops the rest. "
                   "Close to Markov, not exactly."),
        Model("counts", "Tokens in base, on the track, at home", False,
              state="per player: how many tokens are in base, on the ring and at home, "
                    "and the die",
              size="a few thousand positions",
              actions="bring a token out, or move one 'on the track' (which one?)",
              transition="unknown without the squares",
              reward="+1 / -1 at the end",
              note="Easy to read, but it throws away every distance. Capturing and "
                   "stepping out of reach depend on exact squares, so two positions "
                   "with the same counts can need opposite moves."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Moves whatever, whenever. Bless him.", 1, icon="dice"),
        Bot("sven", "Sprint Sven", "Tunnel vision: always pushes his lead token.", 2,
            cards=("front",), icon="race"),
        Bot("hugo", "Hunter Hugo", "Lives for the capture and keeps fresh tokens coming.", 3,
            cards=("hunt", "enter", "front"), icon="sword"),
        Bot("greta", "Grandmaster Greta", "Decades of family-table dominance in five rules.",
            4, cards=("home", "hunt", "enter", "dodge", "front"), icon="crown"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-sven", "Beat Sprint Sven", "win", 1, bot="sven"),
        Challenge("cards", "Open the strategy cards lens", "lens", 1, lens="cards"),
        Challenge("beat-greta", "Beat Grandmaster Greta", "win", 2, bot="greta"),
        Challenge("stack-vs-hugo", "Build a card stack that beats Hunter Hugo in 55 of 100 "
                  "games", "sim", 3, bot="hugo", value=0.55),
    )

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.num_players = self.p["players"]
        #: Start square (ring index) of each seat.
        self.start = [ARM_START[arm] for arm in SEAT_ARMS[self.num_players]]

    # --------------------------------------------------------------- geometry
    def square_of(self, seat: int, progress: int) -> int | None:
        """Ring index of a token's square, or ``None`` in the base or home cells."""
        if 0 <= progress < RING:
            return (self.start[seat] + progress) % RING
        return None

    def victim(self, s: MaednState, seat: int, dest: int) -> tuple[int, int] | None:
        """The opponent token ``(seat, progress)`` captured by landing on ``dest``."""
        square = self.square_of(seat, dest)
        if square is None:
            return None
        for other in range(self.num_players):
            if other != seat:
                theirs = (square - self.start[other]) % RING
                if theirs in s.tokens[other]:
                    return other, theirs
        return None

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> MaednState:
        first = 0 if self.p["start_token"] else BASE
        tokens = [sorted([first] + [BASE] * 3) for _ in range(self.num_players)]
        return self._begin_turn(MaednState(tokens=tokens), 0)

    def is_terminal(self, s: MaednState) -> bool:
        return s.won >= 0

    def winner(self, s: MaednState) -> int | None:
        return s.won if s.won >= 0 else None

    def chance_outcomes(self, s: MaednState) -> list[tuple[Action, float]]:
        return self.die_outcomes()

    def moves(self, s: MaednState, seat: int, die: int) -> list[int]:
        """Legal moves of ``seat`` for ``die``: positions of tokens (``ENTER`` = from base)."""
        mine = s.tokens[seat]
        in_base = mine.count(BASE)
        out: list[int] = []
        if die == 6 and in_base and 0 not in mine:
            out.append(ENTER)
        for q in sorted(set(mine)):
            if q != BASE and q + die <= LAST_PROGRESS and q + die not in mine:
                out.append(q)
        if self.p["forced_entry"] and in_base:
            if 0 in mine and 0 in out:
                return [0]                      # clear the start square first
            if ENTER in out:
                return [ENTER]
        if self.p["must_capture"]:
            captures = [q for q in out if self.victim(s, seat, 0 if q == ENTER else q + die)]
            if captures:
                return captures
        return out

    def legal_actions(self, s: MaednState) -> list[Action]:
        return self.moves(s, s.turn, s.die)

    def _can_try_thrice(self, s: MaednState, seat: int) -> bool:
        """Official three-tries condition: nothing on the track and nothing to advance at home."""
        mine = s.tokens[seat]
        if any(0 <= q < RING for q in mine):
            return False
        return all(all(r in mine for r in range(q + 1, LAST_PROGRESS + 1))
                   for q in mine if q >= HOME_FIRST)

    def _begin_turn(self, s: MaednState, seat: int) -> MaednState:
        s.turn = seat
        s.to_move = CHANCE
        s.tries = 3 if self.p["three_tries"] and self._can_try_thrice(s, seat) else 1
        return s

    def resolve_chance(self, s: MaednState, a: Action) -> None:
        s.die = int(a)
        if self.moves(s, s.turn, s.die):
            s.to_move = s.turn
        elif s.tries > 1:
            s.tries -= 1
            s.to_move = CHANCE                  # try again for a 6
        else:
            self._begin_turn(s, (s.turn + 1) % self.num_players)

    def play(self, s: MaednState, a: Action) -> None:
        seat, die = s.turn, s.die
        src = int(a)
        dest = 0 if src == ENTER else src + die
        mine = s.tokens[seat]
        victim = self.victim(s, seat, dest)
        mine.remove(src)
        mine.append(dest)
        mine.sort()
        if victim is not None:
            other, at = victim
            s.tokens[other].remove(at)
            s.tokens[other].append(BASE)
            s.tokens[other].sort()
        s.last = (seat, dest)
        if mine[0] >= HOME_FIRST:
            s.won = seat
            return
        self._begin_turn(s, seat if die == 6 else (seat + 1) % self.num_players)

    # ------------------------------------------------------------ analysis hooks
    def key(self, s: MaednState):
        return (tuple(tuple(t) for t in s.tokens), s.turn, s.to_move, s.die, s.tries, s.won)

    def standing(self, s: MaednState, seat: int) -> float:
        return float(sum(q + 1 for q in s.tokens[seat]))

    def heuristic(self, s: MaednState, player: int) -> float:
        others = [self.standing(s, o) for o in range(self.num_players) if o != player]
        return self.squash(self.standing(s, player) - sum(others) / len(others), 25)

    # --------------------------------------------------------------- rule cards
    def _dest(self, s: MaednState, action: int) -> int:
        return 0 if action == ENTER else action + s.die

    @pick("enter", "Fresh legs", "Rolled a 6? Bring a new token onto the board.", "flag")
    def card_enter(self, s: MaednState, candidates, player, rng):
        return ENTER if ENTER in candidates else None

    @pick("hunt", "Headhunter",
          "If you can capture an opponent's token, do it, the furthest one first.", "sword")
    def card_hunt(self, s: MaednState, candidates, player, rng):
        best, best_progress = None, -1
        for a in candidates:
            hit = self.victim(s, player, self._dest(s, a))
            if hit is not None and hit[1] > best_progress:
                best, best_progress = a, hit[1]
        return best

    @pick("home", "Safe harbor", "Move a token into your home cells whenever you can.", "home")
    def card_home(self, s: MaednState, candidates, player, rng):
        entering = [a for a in candidates if 0 <= a < RING and a + s.die >= HOME_FIRST]
        return max(entering) if entering else None

    @avoid("dodge", "Out of reach",
           "Avoid stopping 1 to 6 squares in front of an opponent's token.", "shield")
    def card_dodge(self, s: MaednState, action, player):
        square = self.square_of(player, self._dest(s, action))
        if square is None:
            return False
        for other in range(self.num_players):
            if other == player:
                continue
            for q in s.tokens[other]:
                behind = self.square_of(other, q)
                if behind is not None and 1 <= (square - behind) % RING <= 6:
                    return True
        return False

    @pick("front", "Front runner", "Push your most advanced token on the track.", "race")
    def card_front(self, s: MaednState, candidates, player, rng):
        track = [a for a in candidates if 0 <= a < RING]
        return max(track) if track else None

    @pick("rear", "Rear guard",
          "Push your least advanced token on the track and keep the pack together.",
          "footprints")
    def card_rear(self, s: MaednState, candidates, player, rng):
        track = [a for a in candidates if 0 <= a < RING]
        return min(track) if track else None

    @pick("clear-start", "Clear the start",
          "A token on your start square blocks the next 6. Move it on first.", "barrier")
    def card_clear_start(self, s: MaednState, candidates, player, rng):
        return 0 if 0 in candidates else None

    # ------------------------------------------------------------ presentation
    @staticmethod
    def _spot(progress: int) -> str:
        if progress == BASE:
            return "the base"
        if progress >= HOME_FIRST:
            return f"home cell {progress - HOME_FIRST + 1}"
        return f"step {progress + 1}"

    def move_label(self, s: MaednState, a: Action) -> str:
        if a == ENTER:
            return "Bring a token out"
        text = f"Move from {self._spot(int(a))} to {self._spot(int(a) + s.die)}"
        return text + (" and capture" if self.victim(s, s.turn, int(a) + s.die) else "")

    def describe(self, s: MaednState, a: Action, player: int) -> str:
        again = " and rolls again" if s.die == 6 else ""
        dest = self._dest(s, int(a))
        hit = self.victim(s, player, dest)
        kick = f" and kicks {self.seat_label(hit[0])}'s token back to base" if hit else ""
        if a == ENTER:
            return f"brings a token out{kick}{again}"
        if dest >= HOME_FIRST and int(a) >= HOME_FIRST:
            return f"moves a token {s.die} cells inside the home{again}"
        if dest >= HOME_FIRST:
            return f"moves a token {s.die} squares into the home cells{again}"
        return f"moves a token {s.die} squares{kick}{again}"

    def describe_chance(self, s: MaednState, a: Action) -> str:
        text = f"rolls a {a}"
        if not self.moves(s, s.turn, int(a)):
            more = f", tries again ({s.tries - 1} left)" if s.tries > 1 else ""
            return f"{text}: no move{more}"
        return text

    def status(self, s: MaednState, viewer: int | None) -> str:
        if self.is_terminal(s):
            if viewer is None:
                return f"{self.seat_label(s.won)} brings all four tokens home"
            return "All four tokens home: you win" if s.won == viewer else \
                f"{self.seat_label(s.won)} brings all four tokens home"
        if s.to_move == CHANCE:
            return "The die is rolling"
        if s.turn == viewer:
            many = len(self.legal_actions(s)) > 1
            return f"You rolled a {s.die}: " + ("choose a token" if many else "one legal move")
        return f"{self.seat_name(s.turn, viewer)} rolled a {s.die} and is moving"

    def insight(self, stats: dict) -> str | None:
        n = max(1, stats["n"])
        mine, theirs = stats["wins"][0], stats["wins"][1]
        cards = stats.get("cards")
        if cards is not None and "enter" not in cards and mine < theirs:
            return ("Tokens stuck in the base score nothing. Without a Fresh legs card your "
                    "stack only brings tokens out by accident. Most strong stacks start with "
                    "entering, capturing and getting home safely. The order is the interesting "
                    "part.")
        if mine >= 0.6 * n:
            return ("Strong showing. Unlike Tic-Tac-Toe there is no known perfect policy here. "
                    "Dice keep the outcome noisy, but good priorities (capture, enter, stay out "
                    "of reach) shift the odds far more than in Snakes & Ladders. This game sits "
                    "between luck and skill.")
        return None

    # ------------------------------------------------------------------ scene
    def _cell_of(self, seat: int, progress: int, slot: int = 0) -> int:
        arm = SEAT_ARMS[self.num_players][seat]
        if progress == BASE:
            return _grid_index(BASE_CELLS[arm][slot])
        if progress >= HOME_FIRST:
            return _grid_index(HOME_CELLS[arm][progress - HOME_FIRST])
        return _grid_index(RING_CELLS[(ARM_START[arm] + progress) % RING])

    def _board(self, s: MaednState, viewer: int | None) -> dict:
        cells = [None if c is None else dict(c) for c in _template(self.num_players)]
        for seat, tokens in enumerate(s.tokens):
            slot = 0
            for q in tokens:
                idx = self._cell_of(seat, q, slot)
                if q == BASE:
                    slot += 1
                cells[idx].setdefault("pieces", []).append(scene.piece(seat, "token"))
        if s.last is not None:
            seat, dest = s.last
            spot = cells[self._cell_of(seat, dest)]
            if not spot.get("tone"):
                spot["tone"] = "last"
        if not self.is_terminal(s) and s.to_move >= 0 and viewer in (None, s.to_move):
            seat = s.to_move
            slot_of_base = self._cell_of(seat, BASE, 0)
            for a in self.legal_actions(s):
                src = slot_of_base if a == ENTER else self._cell_of(seat, a)
                cells[src]["action"] = a
                cells[self._cell_of(seat, self._dest(s, a))]["action"] = a
        return scene.grid(11, 11, cells, style="tiles")

    def scene(self, s: MaednState, viewer: int | None) -> dict:
        parts = [self._board(s, viewer)]
        if s.die:
            roller = self.seat_name(s.turn, viewer)
            parts.append(self.dice_part([s.die], fresh=s.fresh,
                                        caption=f"{roller} rolled" if s.fresh else "Last roll"))

        def home(i: int) -> int:
            return sum(1 for q in s.tokens[i] if q >= HOME_FIRST)

        def sub(i: int) -> str:
            base = s.tokens[i].count(BASE)
            return f"{4 - home(i) - base} on the track, {base} in base"

        players = self.scoreboard(s, viewer, score=lambda i: f"{home(i)} of 4 home", sub=sub)
        return scene.scene(parts, players=players, status=self.status(s, viewer))
