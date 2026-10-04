"""Tic-Tac-Toe: the hello world of solved games.

The reference implementation for new games: everything generic comes from
:class:`~strategy_lab.families.board.MNKGame` (rules, symmetry, the
"Finish it" / "Block the win" / "Take the center" cards). This file only
adds what is special about 3x3: named squares, the fork cards and the
bots. With the right card order (win, block, fork, smother forks, center,
mirror corner, corner, edge) play is perfect and every game is a draw.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Model, Rulebook, pick
from strategy_lab.families.board import MNKGame, MNKState

CORNERS = (0, 2, 6, 8)
EDGES = (1, 3, 5, 7)
OPPOSITE = {0: 8, 2: 6, 6: 2, 8: 0}
NAMES = ("top-left", "top", "top-right", "left", "center", "right",
         "bottom-left", "bottom", "bottom-right")


class TicTacToe(MNKGame):
    id = "tictactoe"
    name = "Tic-Tac-Toe"
    icon = "grid3"
    tagline = "The classic 3x3 duel. Solved since forever. Can you re-solve it?"
    chapter = "trees"
    order = 20
    concepts = ("game-tree", "minimax", "symmetry", "solved-game", "rule-cards")
    rows, cols, k = 3, 3, 3

    rulebook = Rulebook(
        summary="Two players, X and O, take turns marking a 3x3 grid. X moves first.",
        steps=(
            ("The board", "Nine empty squares. On your turn, put your mark on any empty one."),
            ("Winning", "Three of your marks in a row, column or diagonal win at once."),
            ("Draw", "Nine full squares and no line: a draw. With perfect play from "
                     "both sides, every game ends this way."),
        ),
    )

    models = (
        Model("raw", "Raw board", True,
              state="the 3x3 board plus whose turn it is",
              size="5478 reachable positions",
              actions="the empty squares (at most 9)",
              transition="your mark lands, then the opponent replies: from your seat "
                         "the opponent is part of the environment",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="honest and simple, but every rotation and mirror of a position "
                   "is learned separately."),
        Model("folded", "Symmetry-folded board", True,
              state="one canonical board per class of rotations and mirrors (D4)",
              size="765 positions: about 7x fewer",
              actions="one move per equivalence class (the opening has 3: center, "
                      "corner, edge)",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="same game, far fewer states: symmetry is free generalization."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Plays completely random squares.", 1, icon="dice"),
        Bot("gus", "Greedy Gus", "Takes a win when he sees one. Otherwise: vibes.", 2,
            cards=("win",), icon="smile"),
        Bot("carla", "Careful Carla", "Wins when she can and blocks your wins. No plan "
            "beyond that.", 3, cards=("win", "block"), icon="shield"),
        Bot("minnie", "Minnie Max", "Textbook perfect play. She cannot be beaten, "
            "only drawn.", 4,
            cards=("win", "block", "fork", "smother", "center", "mirror-corner",
                   "corner", "edge"), icon="robot"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-carla", "Beat Careful Carla", "win", 1, bot="carla"),
        Challenge("tree", "Open the game-tree lens", "lens", 1, lens="tree"),
        Challenge("draw-minnie", "Hold Minnie Max to a draw", "draw", 2, bot="minnie"),
        Challenge("perfect-stack", "Build a card stack that never loses to Minnie "
                  "Max in 100 games", "sim", 3, bot="minnie", metric="no_loss"),
    )

    # --------------------------------------------------------- presentation
    def cell_name(self, cell: int) -> str:
        return NAMES[cell]

    def action_label(self, s, a) -> str:
        return NAMES[int(a)]

    def describe(self, s, a, player) -> str:
        return f"places {self.seat_label(player)} in the {NAMES[int(a)]} square"

    # ----------------------------------------------------------- rule cards
    def _makes_fork(self, board: list, cell: int, player: int) -> bool:
        board[cell] = player
        fork = len(self.threats(board, player)) >= 2
        board[cell] = None
        return fork

    @pick("fork", "Build a fork",
          "Create two winning threats at once. Only one can be blocked.", "fork")
    def card_fork(self, s: MNKState, candidates, player, rng):
        b = s.board[:]
        return next((a for a in candidates if self._makes_fork(b, a, player)), None)

    @pick("smother", "Smother forks",
          "Stop the opponent from setting up a double threat.", "barrier")
    def card_smother(self, s: MNKState, candidates, player, rng):
        opp = 1 - player
        b = s.board[:]
        forks = [a for a in candidates if self._makes_fork(b, a, opp)]
        if not forks:
            return None
        if len(forks) == 1:
            return forks[0]
        # Several fork squares: taking one leaves another. Force a defense
        # instead: make a two-in-a-row whose completion square is not a
        # fork square for the opponent.
        for a in candidates:
            b[a] = player
            completions = self.threats(b, player)
            safe = bool(completions) and all(not self._makes_fork(b, e, opp)
                                             for e in completions)
            b[a] = None
            if safe:
                return a
        return forks[0]

    @pick("mirror-corner", "Mirror corner",
          "If the opponent holds a corner, take the one diagonally opposite.", "mirror")
    def card_mirror_corner(self, s, candidates, player, rng):
        for c in CORNERS:
            if s.board[c] == 1 - player and OPPOSITE[c] in candidates:
                return OPPOSITE[c]
        return None

    @pick("corner", "Grab a corner", "Corners sit on three lines each.", "corner")
    def card_corner(self, s, candidates, player, rng):
        cs = [a for a in candidates if a in CORNERS]
        return rng.choice(cs) if cs else None

    @pick("edge", "Take an edge", "Settle for a side square.", "edge")
    def card_edge(self, s, candidates, player, rng):
        es = [a for a in candidates if a in EDGES]
        return rng.choice(es) if es else None
