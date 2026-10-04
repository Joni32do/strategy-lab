"""Backgammon on the OpenSpiel engine.

Rules, dice and move generation come from ``pyspiel``. OpenSpiel's unit of
play is a *whole turn*: one action is the complete way to play both dice
(``24/23 13/10``); a double is two such actions in a row. The dice are
explicit chance nodes, so the odds lens can show the 36 equally likely rolls.

Seats: seat 0 is X, seat 1 is O (OpenSpiel's player ids). X moves from
position 0 up to 23 and bears off past 23, O moves from 23 down to 0. Move
labels use the usual notation where each side counts its own points down
from 24 (X point ``p`` is position ``24 - p``, O point ``p`` is position
``p - 1``).

Reading the board
-----------------
The engine only prints a text diagram, which cannot show stacks of more than
five without ambiguity. The adapter therefore decodes the observation tensor:
per player 24 positions of four numbers (``count==1``, ``==2``, ``==3``,
``count-3``), then bar, borne-off, to-move flags and the dice.

Custom scene part ``backgammon``
--------------------------------
::

    {"view": "backgammon",
     "points": [{"pos": 0, "n": 2, "owner": 0}, ...],   # 24 entries, pos 0..23;
                                                        # n = 0 and owner absent if empty
     "bar":  [x_checkers, o_checkers],
     "off":  [x_borne_off, o_borne_off],
     "pips": [x_pip_count, o_pip_count],
     "turn": 0 | 1 | null,                              # seat that must move now
     "seat": viewer seat | null,
     "layout": {"top": [12, 13, ..., 23], "bottom": [11, 10, ..., 0]},
     "numbering": {"0": "24 - pos", "1": "pos + 1"},    # each side's own point number
     "moves": [{"action": 1279, "label": "24/23 13/10",
                "steps": [{"from": 0, "to": 1, "hit": false}, ...]}]}

``layout`` is OpenSpiel's own diagram: positions 12..23 left to right along
the top, 11..0 left to right along the bottom (so position 0 is the bottom
right corner). ``steps`` use positions, ``"bar"`` as a start and ``"off"`` as an
end. ``moves`` lists the legal turns of the seat to move (empty otherwise);
a view may draw the arrows of a hovered move. Every move is also a plain
action in the action bar. The dice come as a stock ``scene.dice`` part.
"""

from __future__ import annotations

import math
import re

import pyspiel

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, SearchPolicy, scene
from strategy_lab.core.game import Action
from strategy_lab.families.external import SpielGame

POINTS = 24
#: Checkers on the bar count as 25 pips away from bearing off.
BAR_PIPS = 25
_ROLL = re.compile(r"roll: (\d)(\d)")
_PREFIX = re.compile(r"^\d+ - ")


def decode_board(s: pyspiel.State) -> dict:
    """Read checkers, bar, borne-off checkers and dice from the observation tensor."""
    t = s.observation_tensor(0)          # player 0's view: [X board, O board, extras]

    def counts(offset: int) -> list[int]:
        out = []
        for pos in range(POINTS):
            one, two, three, more = t[offset + 4 * pos: offset + 4 * pos + 4]
            out.append(1 if one else 2 if two else 3 if three else 3 + int(more) if more else 0)
        return out

    extras = 2 * POINTS * 4
    dice = [int(v) for v in t[extras + 6: extras + 8] if v]
    return {
        "board": [counts(0), counts(POINTS * 4)],
        "bar": [int(t[extras]), int(t[extras + 3])],
        "off": [int(t[extras + 1]), int(t[extras + 4])],
        "dice": dice,
    }


def pip_counts(info: dict) -> list[int]:
    """Pips each side still has to move before it can bear off everything."""
    x_board, o_board = info["board"]
    x = sum(n * (POINTS - pos) for pos, n in enumerate(x_board)) + BAR_PIPS * info["bar"][0]
    o = sum(n * (pos + 1) for pos, n in enumerate(o_board)) + BAR_PIPS * info["bar"][1]
    return [x, o]


def parse_steps(label: str, player: int) -> list[dict]:
    """Turn a label such as ``"24/21*/20 6/5(2)"`` into checker steps.

    Positions are engine positions; the start may be ``"bar"`` and the end
    ``"off"``. Returns an empty list for ``Pass`` or anything unreadable.
    """
    def pos(token: str):
        if token == "Bar":
            return "bar"
        if token == "Off":
            return "off"
        point = int(token)
        return POINTS - point if player == 0 else point - 1

    steps: list[dict] = []
    try:
        for token in label.split():
            repeat = 1
            if token.endswith(")") and "(" in token:
                token, times = token[:-1].split("(")
                repeat = int(times)
            chain = token.split("/")
            hops = []
            for i in range(len(chain) - 1):
                hit = chain[i + 1].endswith("*")
                hops.append({"from": pos(chain[i].rstrip("*")),
                             "to": pos(chain[i + 1].rstrip("*")), "hit": hit})
            steps.extend(hops * repeat)
    except ValueError:
        return []
    return steps


class Backgammon(SpielGame):
    id = "backgammon"
    name = "Backgammon"
    icon = "race"
    tagline = "A race with a knife fight inside. You choose, the dice answer."
    chapter = "dice-and-choice"
    order = 20
    concepts = ("expectimax", "probability", "distribution-of-sums", "risk",
                "luck-vs-skill", "markov-property", "monte-carlo", "mcts")
    spiel_name = "backgammon"
    seat_names = ("X", "O")
    forward_params = ("scoring_type", "hyper_backgammon")
    chance_word = "Rolling"
    #: Two players need about 120 turns, 2 steps each (roll and move).
    max_steps = 800
    #: The conformance suite plays every MCTS bot on both sides; keep that fast.
    conformance_steps = 40

    params = {
        "scoring_type": Param(
            "winloss_scoring", "Scoring",
            "winloss_scoring: every win is worth 1. enable_gammons: a gammon is worth 2. "
            "full_scoring: a backgammon is worth 3.",
            choices=("winloss_scoring", "enable_gammons", "full_scoring")),
        "hyper_backgammon": Param(
            False, "Hyper-backgammon",
            "Each side starts with 3 checkers in its own home board: games last minutes."),
    }

    rulebook = Rulebook(
        summary="A two-player race game for 15 checkers each, moved by the roll of two "
                "dice. The first player to bear off all 15 wins.",
        steps=(
            ("The board", "A track of 24 points in four quadrants of 6. Each side starts "
                          "with 15 checkers on fixed points and moves them in opposite "
                          "directions around the board toward its own home board (the "
                          "last 6 points)."),
            ("Rolling and moving", "Each turn you roll two dice and move checkers that "
                                   "many points in your direction: one checker per die, "
                                   "or one checker the sum of both, as long as every "
                                   "stop is a legal landing point. Doubles (5-5) give "
                                   "four moves of that number instead of two."),
            ("Landing rules", "You may land on an empty point, on a point with your own "
                              "checkers, or on a point with exactly one enemy checker (a "
                              "blot): that hits it. You may never land on a point with "
                              "two or more enemy checkers."),
            ("Hitting and the bar", "A hit checker goes to the bar. It must re-enter in "
                                    "the opponent's home board before you may move any "
                                    "other checker. Points the opponent holds with two or "
                                    "more checkers are blocked."),
            ("Bearing off", "Once all 15 of your checkers are in your home board, you "
                            "may take them off: a checker whose point matches a die "
                            "exactly, or one from a lower point when no checker sits on "
                            "the exact number and the higher points are empty."),
            ("Scoring", "A normal win scores 1 point. A gammon (the loser has borne off "
                        "nothing) scores 2, a backgammon (the loser still has a checker on "
                        "the bar or in the winner's home board) scores 3. Gammons count "
                        "only when you switch the scoring parameter on."),
        ),
        extra=(
            ("One action per turn", "OpenSpiel treats a whole turn as one action, so the "
                                    "action bar lists complete plays such as 24/23 13/10. "
                                    "A double is two such plays in a row."),
            ("No doubling cube", "Money and match play add a cube marked 2, 4, 8 ... The "
                                 "lab plays single games and does not use the cube."),
        ),
        source="https://www.bkgm.com/rules.html",
    )

    models = (
        Model("checkers-only", "Checker positions only (no dice)", False,
              state="the 24 points plus bar and off, with each checker's position, but "
                    "not the roll you have to play",
              actions="none can be listed: which moves exist depends entirely on the dice",
              reward="+1 / -1 (+2 / +3 for gammon / backgammon) at the end; gamma = 1",
              note="it looks like the state because it is everything you can see, but it "
                   "is useless on its own: you cannot name one legal move without the "
                   "roll, so it is not Markov for the decision problem."),
        Model("board-dice", "Board + current dice to play", True,
              state="checker positions (24 points, bar, off) for both sides plus the "
                    "roll you must play this turn",
              size="roughly 10^20 reachable positions x 21 distinct rolls",
              actions="the legal ways to play the roll: which checkers move, forced bar "
                      "entry, forced single moves when one die cannot be played",
              transition="you play the roll, then the dice choose the opponent's roll "
                         "(36 equally likely outcomes), then the opponent plays it",
              reward="+1 win / -1 loss (doubled for a gammon, tripled for a backgammon "
                     "if switched on); gamma = 1",
              note="this is the state OpenSpiel works with for a single game: board plus "
                   "roll is a complete decision point."),
        Model("cube-match", "Board + dice + doubling cube + match score", True,
              state="board + dice to play, plus the cube value and owner, plus the "
                    "running score and the match length",
              actions="legal checker plays, plus offering or taking a double when the "
                      "cube is live",
              reward="match-adjusted equity rather than a flat +-1/2/3: the same position "
                     "can call for a different move near match point than early in a "
                     "money game",
              note="the full tournament formulation. Single games do not need the cube "
                   "or the score, but any serious engine tracks them. The cube alone "
                   "roughly doubles the size of the decision problem."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Plays a random legal turn. Leaves blots everywhere.",
            1, icon="dice"),
        Bot("pete", "Pip Pete", "Counts pips and hits when he can. Sometimes he even "
            "remembers to cover his blots.", 2, policy="pete_policy", icon="timer"),
        Bot("monte", "Monte", "Plays 40 random games from every turn and takes the best "
            "average. Noisy, but he sees hits coming.", 3, policy="monte_policy",
            icon="dice"),
        Bot("monty", "Monty Carlo", "The same trick with 200 games per turn. Slow, steady "
            "and hard to bluff because he cannot be bluffed.", 4, policy="monty_policy",
            icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("odds", "Open the odds lens", "lens", 1, lens="odds"),
        Challenge("beat-pete", "Beat Pip Pete", "win", 1, bot="pete"),
        Challenge("beat-monte", "Beat Monte", "win", 2, bot="monte"),
        Challenge("beat-monty", "Beat Monty Carlo", "win", 3, bot="monty"),
    )

    # ----------------------------------------------------------------- search
    def heuristic(self, s: pyspiel.State, player: int) -> float:
        """Pip lead, blots, bar and borne-off checkers of ``player``, in ``(-1, 1)``."""
        info = decode_board(s)
        mine, theirs = pip_counts(info)[player], pip_counts(info)[1 - player]
        blots = [sum(1 for n in side if n == 1) for side in info["board"]]
        score = ((theirs - mine) / 40
                 + 0.15 * (blots[1 - player] - blots[player])
                 + 0.20 * (info["bar"][1 - player] - info["bar"][player])
                 + 0.10 * (info["off"][player] - info["off"][1 - player]))
        return math.tanh(score)

    def pete_policy(self):
        return SearchPolicy(depth=1, name="Pip Pete")

    def monte_policy(self):
        return self.mcts(40, name="Monte")

    def monty_policy(self):
        return self.mcts(200, name="Monty Carlo")

    # ----------------------------------------------------------- presentation
    def action_label(self, s: pyspiel.State, a: Action) -> str:
        raw = super().action_label(s, a)
        if s.current_player() == CHANCE:
            roll = _ROLL.search(raw)
            return f"{roll.group(1)}-{roll.group(2)}" if roll else raw
        return _PREFIX.sub("", raw)

    def describe(self, s, a, player) -> str:
        label = self.action_label(s, a)
        return "cannot move" if label == "Pass" else f"plays {label}"

    def describe_chance(self, s, a) -> str:
        raw = s.action_to_string(CHANCE, int(a))
        roll = _ROLL.search(raw)
        dice = f"{roll.group(1)} and {roll.group(2)}" if roll else ""
        if "starts" in raw:
            starter = "X" if "X starts" in raw else "O"
            return f"rolls {dice} for the opening: {starter} starts"
        return f"rolls {dice}"

    def status(self, s, viewer) -> str:
        if self.is_terminal(s):
            return super().status(s, viewer)
        p = self.current_player(s)
        if p == CHANCE:
            return "Rolling the dice..."
        dice = decode_board(s)["dice"]
        roll = " and ".join(str(v if v <= 6 else v - 6) for v in dice)
        who = "Your move" if viewer == p else f"{self.seat_label(p)} to move"
        return f"{who}: roll {roll}" if roll else who

    def scene(self, s: pyspiel.State, viewer):
        info = decode_board(s)
        terminal = self.is_terminal(s)
        player = self.current_player(s)
        points = []
        for pos in range(POINTS):
            x, o = info["board"][0][pos], info["board"][1][pos]
            entry = {"pos": pos, "n": x or o}
            if x or o:
                entry["owner"] = 0 if x else 1
            points.append(entry)
        moves = []
        if not terminal and player >= 0 and (viewer is None or viewer == player):
            for a in self.legal_actions(s):
                label = self.action_label(s, a)
                moves.append({"action": a, "label": label, "steps": parse_steps(label, player)})
        board = scene.custom(
            "backgammon", points=points, bar=info["bar"], off=info["off"],
            pips=pip_counts(info), turn=player if player >= 0 else None, seat=viewer,
            layout={"top": list(range(12, 24)), "bottom": list(range(11, -1, -1))},
            numbering={"0": "24 - pos", "1": "pos + 1"}, moves=moves)
        parts = [board]
        if info["dice"]:
            tone = "white" if player in (0, -1) else "red"
            fresh = "Previous player: -1" in str(s)          # the dice were just rolled
            faces = [scene.die(v if v <= 6 else v - 6, tone=tone, held=v > 6)
                     for v in info["dice"]]
            parts.append(scene.dice(faces, fresh=fresh))
        names = [self.seat_label(i) for i in (0, 1)]
        rows = [scene.player(names[i], sub=f"{pip_counts(info)[i]} pips, {info['off'][i]} off",
                             active=(not terminal and player == i), owner=i) for i in (0, 1)]
        return scene.scene(parts, players=rows, status=self.status(s, viewer))
