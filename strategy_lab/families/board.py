"""Board families: games played by placing marks on a grid.

:class:`MNKGame` is the whole k-in-a-row family in one class: an ``m x n``
board, players alternate, the first to line up ``k`` marks wins. With
``gravity`` the marks fall to the lowest free cell of a column.

==============  ====  ====  ===  =======
game            rows  cols  k    gravity
==============  ====  ====  ===  =======
Tic-Tac-Toe     3     3     3    no
Connect Four    6     7     4    yes
Gomoku          15    15    5    no
==============  ====  ====  ===  =======

Everything generic lives here: rules, win detection, the board symmetry
group, a line-counting heuristic, the scene, and the rule cards every
k-in-a-row game shares ("Finish it", "Block the win", "Take the center").
A concrete game sets the four class attributes and adds what is special.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from strategy_lab.core import Game, pick, scene
from strategy_lab.core.game import Action


@dataclass
class MNKState:
    board: list[int | None]
    to_move: int = 0
    last: int | None = None
    win_line: tuple[int, ...] = ()
    moves: int = 0


@lru_cache(maxsize=None)
def _lines(rows: int, cols: int, k: int) -> tuple[tuple[int, ...], ...]:
    """Every run of ``k`` cells in a row, column or diagonal."""
    out = []
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = []
                for i in range(k):
                    rr, cc = r + dr * i, c + dc * i
                    if not (0 <= rr < rows and 0 <= cc < cols):
                        break
                    cells.append(rr * cols + cc)
                if len(cells) == k:
                    out.append(tuple(cells))
    return tuple(out)


@lru_cache(maxsize=None)
def _lines_through(rows: int, cols: int, k: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    by_cell: list[list[tuple[int, ...]]] = [[] for _ in range(rows * cols)]
    for line in _lines(rows, cols, k):
        for c in line:
            by_cell[c].append(line)
    return tuple(tuple(x) for x in by_cell)


@lru_cache(maxsize=None)
def _transforms(rows: int, cols: int, gravity: bool) -> tuple[tuple[int, ...], ...]:
    """Cell permutations ``P`` of the board's symmetry group.

    ``transformed[i] = board[P[i]]``. Square boards get all 8 rotations and
    mirrors (the dihedral group D4); rectangles get the 4 flips; gravity
    boards only the left-right mirror (up and down are not symmetric).
    """
    def perm(f):
        return tuple(f(r, c) for r in range(rows) for c in range(cols))
    ident = perm(lambda r, c: r * cols + c)
    mirror = perm(lambda r, c: r * cols + (cols - 1 - c))
    if gravity:
        return (ident, mirror)
    flip_v = perm(lambda r, c: (rows - 1 - r) * cols + c)
    rot180 = perm(lambda r, c: (rows - 1 - r) * cols + (cols - 1 - c))
    if rows != cols:
        return (ident, mirror, flip_v, rot180)
    n = rows
    group = {ident}
    frontier = [ident]
    rot90 = perm(lambda r, c: (n - 1 - c) * n + r)
    while frontier:
        p = frontier.pop()
        for g in (rot90, mirror):
            q = tuple(p[g[i]] for i in range(n * n))
            if q not in group:
                group.add(q)
                frontier.append(q)
    return tuple(sorted(group))


class MNKGame(Game):
    """Base class of the k-in-a-row family. See the module docstring."""

    family_id = "k-in-a-row"
    family_name = "K in a row"
    family_blurb = ("Same rules, different boards: line up k marks first. "
                    "Tic-Tac-Toe and Connect Four are one class with other numbers.")

    rows: int = 3
    cols: int = 3
    k: int = 3
    gravity: bool = False

    seat_names = ("X", "O")
    #: Piece shapes per seat (``disc`` looks right with gravity).
    shapes: tuple[str, str] = ("x", "o")

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> MNKState:
        return MNKState([None] * (self.rows * self.cols))

    def copy_state(self, s: MNKState) -> MNKState:
        return MNKState(s.board[:], s.to_move, s.last, s.win_line, s.moves)

    def current_player(self, s: MNKState) -> int:
        return s.to_move

    def legal_actions(self, s: MNKState) -> list[Action]:
        if self.gravity:
            return [c for c in range(self.cols) if s.board[c] is None]
        return [i for i, v in enumerate(s.board) if v is None]

    def landing(self, s: MNKState, a: Action) -> int:
        """The cell a move occupies (differs from ``a`` only with gravity)."""
        if not self.gravity:
            return int(a)
        for r in range(self.rows - 1, -1, -1):
            cell = r * self.cols + int(a)
            if s.board[cell] is None:
                return cell
        raise ValueError(f"column {a} is full")

    def move(self, s: MNKState, a: Action) -> None:
        cell = self.landing(s, a)
        me = s.to_move
        s.board[cell] = me
        s.last = cell
        s.moves += 1
        for line in _lines_through(self.rows, self.cols, self.k)[cell]:
            if all(s.board[c] == me for c in line):
                s.win_line = line
                break
        s.to_move = 1 - me

    def is_terminal(self, s: MNKState) -> bool:
        return bool(s.win_line) or s.moves == self.rows * self.cols

    def winner(self, s: MNKState) -> int | None:
        return s.board[s.win_line[0]] if s.win_line else None

    # ---------------------------------------------------------------- helpers
    def wins_now(self, s: MNKState, a: Action, player: int) -> bool:
        """Would ``player`` complete a line by playing ``a``?"""
        cell = self.landing(s, a)
        for line in _lines_through(self.rows, self.cols, self.k)[cell]:
            if all(c == cell or s.board[c] == player for c in line):
                return True
        return False

    def threats(self, board: list[int | None], player: int) -> set[int]:
        """Empty cells that would complete a line for ``player``."""
        out = set()
        for line in _lines(self.rows, self.cols, self.k):
            empty = [c for c in line if board[c] is None]
            if len(empty) == 1 and all(board[c] == player for c in line if c != empty[0]):
                out.add(empty[0])
        return out

    def cell_name(self, cell: int) -> str:
        r, c = divmod(cell, self.cols)
        return f"{'abcdefghijklmnopqrstuvwxyz'[c]}{self.rows - r}"

    # --------------------------------------------------------------- symmetry
    def key(self, s: MNKState) -> str:
        return "".join("." if v is None else "XO"[v] for v in s.board) + str(s.to_move)

    def canonical_key(self, s: MNKState) -> str:
        b = s.board
        return min("".join("." if b[p[i]] is None else "XO"[b[p[i]]] for i in range(len(b)))
                   for p in _transforms(self.rows, self.cols, self.gravity)) + str(s.to_move)

    def action_classes(self, s: MNKState, actions: list[Action]) -> list[list[Action]]:
        """Moves that are the same decision up to a symmetry of the board."""
        b = s.board
        stab = [p for p in _transforms(self.rows, self.cols, self.gravity)
                if all(b[p[i]] == b[i] for i in range(len(b)))]
        parent = {a: a for a in actions}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for p in stab:
            for a in actions:
                if self.gravity:
                    img = (self.cols - 1 - a) if p[0] != 0 else a
                else:
                    img = p[a]
                if img in parent:
                    parent[find(a)] = find(img)
        classes: dict = {}
        for a in actions:
            classes.setdefault(find(a), []).append(a)
        return sorted(classes.values(), key=lambda c: min(c))

    # -------------------------------------------------------------- heuristic
    def heuristic(self, s: MNKState, player: int) -> float:
        """Open lines weighted by how full they are, squashed to ``(-1, 1)``."""
        score = 0.0
        for line in _lines(self.rows, self.cols, self.k):
            mine = sum(1 for c in line if s.board[c] == player)
            theirs = sum(1 for c in line if s.board[c] == 1 - player)
            if mine and not theirs:
                score += 4 ** mine
            elif theirs and not mine:
                score -= 4 ** theirs
        return math.tanh(score / (4 ** self.k))

    # ------------------------------------------------------------ rule cards
    @pick("win", "Finish it", "If a move completes your line right now, play it.", "trophy")
    def card_win(self, s, candidates, player, rng):
        return next((a for a in candidates if self.wins_now(s, a, player)), None)

    @pick("block", "Block the win",
          "If the opponent could complete a line next turn, take that spot first.", "shield")
    def card_block(self, s, candidates, player, rng):
        return next((a for a in candidates if self.wins_now(s, a, 1 - player)), None)

    @pick("center", "Take the center",
          "The middle sits on the most lines. Grab it while it is free.", "target")
    def card_center(self, s, candidates, player, rng):
        if self.gravity:
            mid = self.cols // 2 if self.cols % 2 else None
            return mid if mid in candidates else None
        if self.rows % 2 and self.cols % 2:
            mid = (self.rows // 2) * self.cols + self.cols // 2
            return mid if mid in candidates else None
        return None

    # ----------------------------------------------------------- presentation
    def action_label(self, s, a) -> str:
        return f"column {int(a) + 1}" if self.gravity else self.cell_name(int(a))

    def describe(self, s, a, player) -> str:
        mark = self.seat_label(player)
        if self.gravity:
            return f"drops {mark} into column {int(a) + 1}"
        return f"places {mark} on {self.cell_name(int(a))}"

    def scene(self, s: MNKState, viewer):
        legal = set(self.legal_actions(s)) if not self.is_terminal(s) else set()
        cells = []
        for i, v in enumerate(s.board):
            col = i % self.cols
            if self.gravity:
                action = col if col in legal else None
            else:
                action = i if i in legal else None
            pcs = [scene.piece(v, self.shapes[v])] if v is not None else []
            cells.append(scene.cell(pieces=pcs, action=action,
                                    tone="last" if i == s.last else ""))
        style = "holes" if self.gravity else "board"
        board = scene.grid(self.rows, self.cols, cells, style=style,
                           lines=[s.win_line] if s.win_line else [])
        return scene.scene([board])
