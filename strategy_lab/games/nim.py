"""Nim: the game that every perfect-information game secretly is.

Heaps of objects, two players, one rule: on your turn take any number of
objects from *one* heap. Whoever takes the last object wins (or loses, in the
misere variant). Nim is small enough to solve completely, and the solution is
a one-line formula: write every heap size in binary and XOR them. This number
is the *nim-sum*. A position is lost for the player to move exactly when the
nim-sum is zero (Bouton, 1901). Every other two-player game without chance
and without hidden information is equivalent to some Nim position (the
Sprague-Grundy theorem), which is why Nim opens the "game trees" chapter.

Design notes
------------
* An action is the string ``"h:n"``: take ``n`` objects from heap ``h``
  (counting from 0). Heaps keep their index, even when empty.
* Heaps are interchangeable. ``canonical_key`` sorts them, and
  ``action_classes`` groups moves on equal heaps, so the solver and the
  game-tree lens see far fewer positions than a naive search would.
* Misere play needs one correction to the nim-sum rule: once every heap has
  at most one object left, the winner is decided by parity instead (see
  :meth:`Nim.is_losing`). Tests check the formula against the exact solver on
  every small position, for both variants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import reduce
from operator import xor

from strategy_lab.core import Bot, Challenge, Game, Model, Param, Rulebook, pick, scene
from strategy_lab.core.game import Action

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_HEAPS = 7
MAX_SIZE = 15


@dataclass
class NimState:
    """The heaps (by index), whose turn it is, and the last move as ``(heap, count)``."""

    heaps: list[int]
    to_move: int = 0
    last: tuple[int, int] | None = None


def nim_sum(heaps) -> int:
    """XOR of all heap sizes. Zero means the player to move is lost (normal play)."""
    return reduce(xor, heaps, 0)


def parse_heaps(text: str) -> list[int]:
    """Read ``"3,4,5"`` (commas, spaces or semicolons) into a list of heap sizes.

    Raises:
        ValueError: unless there are 1 to 7 whole numbers, each between 1 and 15.
    """
    parts = [p for p in re.split(r"[,;\s]+", str(text).strip()) if p]
    try:
        heaps = [int(p) for p in parts]
    except ValueError:
        heaps = []
    if not 1 <= len(heaps) <= MAX_HEAPS or not all(1 <= h <= MAX_SIZE for h in heaps):
        raise ValueError(f"heaps must be 1 to {MAX_HEAPS} whole numbers between 1 and "
                         f"{MAX_SIZE}, like 3,4,5")
    return heaps


def split(action: Action) -> tuple[int, int]:
    """``"2:3"`` -> ``(2, 3)``: heap 2, take 3."""
    heap, count = str(action).split(":")
    return int(heap), int(count)


class Nim(Game):
    id = "nim"
    name = "Nim"
    icon = "sticks"
    tagline = "Take from one heap, take the last object. A one-line formula plays it perfectly."
    chapter = "trees"
    order = 10
    concepts = ("winning-position", "backward-induction", "game-tree", "solved-game",
                "symmetry")

    params = {
        "heaps": Param("3,4,5", "Heaps", "Heap sizes separated by commas, e.g. 3,4,5 or "
                                         "1,3,5,7. Up to 7 heaps of up to 15."),
        "misere": Param(False, "Misere", "Taking the last object loses instead of wins."),
    }

    rulebook = Rulebook(
        summary="Several heaps of objects. Players take turns removing objects from a "
                "single heap. Whoever takes the last object wins.",
        steps=(
            ("The heaps", "The game starts with heaps of 3, 4 and 5 objects. You can set "
                          "your own."),
            ("A move", "Pick one heap and remove one or more objects from it. Never from "
                       "two heaps in one turn."),
            ("Winning", "Take the last object and you win. In the misere variant, taking "
                        "the last object loses."),
        ),
        extra=(
            ("Misere play", "The winning strategy matches normal play until a move would "
                            "leave only heaps of size 1. Then you leave an odd number of "
                            "them."),
            ("Your heaps", "Any 1 to 7 heaps of 1 to 15 objects work, for example 1,3,5,7."),
        ),
        source="https://en.wikipedia.org/wiki/Nim",
    )

    models = (
        Model("heaps", "Heap sizes in order", True,
              state="the heap sizes as a tuple, for example (3, 4, 5)",
              size="120 positions for 3,4,5 (4 x 5 x 6)",
              actions="take n objects from heap h: 12 moves at the start",
              transition="your move changes one heap, then the opponent replies: from "
                         "your seat the opponent is part of the environment",
              reward="+1 for the win, -1 for the loss, at the end; gamma = 1",
              note="Complete and Markov, but (3, 4, 5) and (5, 3, 4) are learned as two "
                   "different positions."),
        Model("sorted", "Sorted heaps", True,
              state="the heap sizes in sorted order (a multiset)",
              size="48 positions for 3,4,5: 2.5 times fewer",
              actions="one move per class of equal heaps",
              transition="same as above",
              reward="+1 for the win, -1 for the loss, at the end; gamma = 1",
              note="Heaps are interchangeable, so sorting is free generalization. It is "
                   "the same idea as folding Tic-Tac-Toe boards by rotation."),
        Model("nimsum", "The nim-sum only", False,
              state="the XOR of all heap sizes (3 bits for 3,4,5)",
              size="8 states",
              actions="take n objects from heap h",
              transition="not decided by the state: positions with the same nim-sum have "
                         "different moves and different futures",
              reward="+1 for the win, -1 for the loss, at the end; gamma = 1",
              note="The nim-sum tells you whether you are winning, not which move wins. "
                   "A great feature but a poor state: this is where the Markov "
                   "property breaks."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Takes a random number from a random heap.", 1,
            icon="dice"),
        Bot("toby", "Take-one Toby", "Takes exactly one object per turn. Patient, "
            "predictable.", 1, cards=("one",), icon="footprints"),
        Bot("bea", "Big-bite Bea", "Swallows the biggest heap whole, every time.", 2,
            cards=("biggest",), icon="pig"),
        Bot("nina", "Nim-sum Nina", "Plays the nim-sum strategy. She never misses a win.",
            4, cards=("nimsum", "one"), icon="sigma"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-toby", "Beat Take-one Toby", "win", 1, bot="toby"),
        Challenge("tree", "Open the game-tree lens", "lens", 1, lens="tree"),
        Challenge("beat-nina", "Beat Nim-sum Nina", "win", 2, bot="nina"),
        Challenge("stack-nina", "Build a card stack that beats Nim-sum Nina in 45% of 100 "
                  "games", "sim", 3, bot="nina", metric="winrate", value=0.45),
    )

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.start = parse_heaps(self.p["heaps"])
        self.misere = bool(self.p["misere"])

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> NimState:
        return NimState(list(self.start))

    def copy_state(self, s: NimState) -> NimState:
        return NimState(s.heaps[:], s.to_move, s.last)

    def current_player(self, s: NimState) -> int:
        return s.to_move

    def legal_actions(self, s: NimState) -> list[Action]:
        return [f"{h}:{n}" for h, count in enumerate(s.heaps) for n in range(1, count + 1)]

    def move(self, s: NimState, a: Action) -> None:
        heap, count = split(a)
        s.heaps[heap] -= count
        s.last = (heap, count)
        s.to_move = 1 - s.to_move

    def is_terminal(self, s: NimState) -> bool:
        return not any(s.heaps)

    def winner(self, s: NimState) -> int | None:
        # After the last move the turn has passed to the player who did NOT take it.
        return s.to_move if self.misere else 1 - s.to_move

    # ---------------------------------------------------------------- theory
    def is_losing(self, heaps) -> bool:
        """Is the player to move lost under perfect play on ``heaps``?

        Normal play: exactly when the nim-sum is zero. Misere play is the
        same, except when every heap has at most one object: then the player
        to move loses exactly when an odd number of heaps remain.
        """
        if self.misere and max(heaps, default=0) <= 1:
            return sum(heaps) % 2 == 1
        return nim_sum(heaps) == 0

    def winning_moves(self, s: NimState) -> list[Action]:
        """Every move that leaves the opponent in a lost position (empty if you are lost)."""
        moves = []
        for h, count in enumerate(s.heaps):
            for n in range(1, count + 1):
                after = s.heaps[:h] + [count - n] + s.heaps[h + 1:]
                if self.is_losing(after):
                    moves.append(f"{h}:{n}")
        return moves

    # --------------------------------------------------------------- symmetry
    def key(self, s: NimState) -> str:
        return ",".join(map(str, s.heaps)) + f"|{s.to_move}"

    def canonical_key(self, s: NimState) -> str:
        """Heaps are interchangeable: sort them."""
        return ",".join(map(str, sorted(s.heaps))) + f"|{s.to_move}"

    def action_classes(self, s: NimState, actions: list[Action]) -> list[list[Action]]:
        """Taking ``n`` from any of several equal heaps is one decision."""
        classes: dict[tuple[int, int], list[Action]] = {}
        for a in actions:
            heap, count = split(a)
            classes.setdefault((s.heaps[heap], count), []).append(a)
        return list(classes.values())

    # ------------------------------------------------------------- rule cards
    @pick("nimsum", "Zero the nim-sum",
          "Move so that the XOR of all heap sizes is zero. Perfect play. In misere play, "
          "near the end leave an odd number of single objects.", "sigma")
    def card_nimsum(self, s, candidates, player, rng):
        moves = [a for a in self.winning_moves(s) if a in candidates]
        return rng.choice(moves) if moves else None

    @pick("biggest", "Take all of the biggest", "Empty the largest heap in one go.", "pig")
    def card_biggest(self, s, candidates, player, rng):
        top = max(s.heaps)
        heaps = [h for h, count in enumerate(s.heaps) if count == top]
        action = f"{rng.choice(heaps)}:{top}"
        return action if action in candidates else None

    @pick("one", "Take one", "Remove a single object from some heap.", "footprints")
    def card_one(self, s, candidates, player, rng):
        singles = [a for a in candidates if split(a)[1] == 1]
        return rng.choice(singles) if singles else None

    @staticmethod
    def _equal_pairs(heaps) -> int:
        """How many pairs of non-empty heaps have the same size."""
        sizes = [c for c in heaps if c > 0]
        return sum(1 for i in range(len(sizes)) for j in range(i + 1, len(sizes))
                   if sizes[i] == sizes[j])

    @pick("even", "Even out",
          "Make two heaps equal. Equal pairs cancel in the nim-sum, so a position made of "
          "pairs is lost for the player to move.", "scale")
    def card_even(self, s, candidates, player, rng):
        before = self._equal_pairs(s.heaps)
        evens = []
        for a in candidates:
            heap, count = split(a)
            after = s.heaps[:heap] + [s.heaps[heap] - count] + s.heaps[heap + 1:]
            if self._equal_pairs(after) > before:
                evens.append(a)
        return rng.choice(evens) if evens else None

    # ----------------------------------------------------------- presentation
    def action_label(self, s, a) -> str:
        heap, count = split(a)
        return f"take {count} from heap {LETTERS[heap]}"

    def describe(self, s, a, player) -> str:
        heap, count = split(a)
        return f"takes {count} from heap {LETTERS[heap]}"

    def status(self, s: NimState, viewer: int | None) -> str:
        if self.is_terminal(s):
            winner = self.winner(s)
            if viewer is None:
                return f"Game over: {self.seat_label(winner)} wins"
            return "You win" if winner == viewer else "You lose"
        last = "loses" if self.misere else "wins"
        if viewer is None or s.to_move != viewer:
            return f"{self.seat_label(s.to_move)} to move. Taking the last object {last}."
        return f"Your move: take from one heap. Taking the last object {last}."

    def scene(self, s: NimState, viewer: int | None) -> dict:
        live = not self.is_terminal(s)
        heaps = [scene.heap(count, LETTERS[h],
                            [f"{h}:{n}" for n in range(1, count + 1)] if live else [])
                 for h, count in enumerate(s.heaps)]
        rule = ("Misere play: whoever takes the last object loses." if self.misere
                else "Normal play: whoever takes the last object wins.")
        if s.last is not None:
            heap, count = s.last
            rule += f" Last move: {count} from heap {LETTERS[heap]}."
        return scene.scene([scene.heaps(heaps, caption=rule)], status=self.status(s, viewer))

    def insight(self, stats: dict) -> str | None:
        if stats.get("bot") != "nina":
            return None
        mine = stats["firstMover"][0]
        verdict = "second" if self.is_losing(self.start) else "first"
        return (f"With perfect play from both sides, the {verdict} player wins from these "
                f"heaps. Your stack started {mine['games']} games and won {mine['wins']} "
                "of them.")
