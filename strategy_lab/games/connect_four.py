"""Connect Four: a game tree too big to solve by hand, small enough to search.

The 6x7 board with gravity is the same family as Tic-Tac-Toe
(:class:`~strategy_lab.families.board.MNKGame`): ``rows, cols, k = 6, 7, 4``
and ``gravity = True``. Everything generic is inherited: rules, win lines,
the mirror symmetry, the line-counting heuristic and the "Finish it", "Block
the win" and "Take the center" cards. This file adds what the bigger board
needs: three more cards and bots that look ahead.

Why it belongs in the "trees" chapter: Connect Four has about 4.5 x 10^12
reachable positions (Tromp), so the exact solver of the game-tree lens gives
up and the lens falls back on depth-limited search with the heuristic. The
game is solved all the same (Allen and Allis, 1988): the first player wins
with perfect play by starting in the middle column. The search bots here
look 2 and 4 plies ahead, so they spot short tactics and miss long plans.
"""

from __future__ import annotations

from strategy_lab.core import Bot, Challenge, Model, Rulebook, SearchPolicy, avoid, pick
from strategy_lab.families.board import MNKGame, MNKState


class ConnectFour(MNKGame):
    id = "connect4"
    name = "Connect Four"
    icon = "discs"
    tagline = "Drop discs, line up four. The first player wins with perfect play."
    chapter = "trees"
    order = 30
    concepts = ("game-tree", "branching-factor", "heuristic", "minimax")

    rows, cols, k, gravity = 6, 7, 4, True
    shapes = ("disc", "disc")
    seat_names = ("Red", "Yellow")

    rulebook = Rulebook(
        summary="Two players drop colored discs into a 7-column, 6-row frame. A disc falls "
                "to the lowest free spot. Four in a row wins.",
        steps=(
            ("The board", "Seven columns, six rows, standing upright. Red moves first."),
            ("A move", "Choose a column. Your disc falls to the lowest empty spot in it."),
            ("Winning", "Four of your discs in a row, column or diagonal win at once."),
            ("Draw", "If all 42 spots fill with no line of four, the game is a draw."),
        ),
        extra=(
            ("Perfect play", "With perfect play the first player wins by starting in the "
                             "middle column. Starting next to it draws, and starting in "
                             "the four outer columns loses."),
        ),
        source="https://en.wikipedia.org/wiki/Connect_Four",
    )

    models = (
        Model("board", "Raw board", True,
              state="the 6x7 grid of red, yellow and empty, plus whose turn it is",
              size="4,531,985,219,092 reachable positions (Tromp)",
              actions="the columns that are not full (at most 7)",
              transition="your disc falls, then the opponent replies: from your seat the "
                         "opponent is part of the environment",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="Complete and Markov, and far too big for a table: every position "
                   "must be generalized from a few seen ones."),
        Model("mirror", "Mirror-folded board", True,
              state="the board or its left-right mirror image, whichever sorts first",
              size="about half as many positions",
              actions="one column per class of mirrored moves",
              transition="same as above",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="Gravity breaks every symmetry except the mirror, so folding saves "
                   "only a factor of two. Compare 7x on the Tic-Tac-Toe board."),
        Model("features", "Line-count features", False,
              state="a few numbers: open twos, open threes and column heights for both "
                    "sides (the heuristic's view)",
              size="a few hundred feature values",
              actions="the columns that are not full",
              transition="not decided by the features: different boards share them and "
                         "have different futures",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="Cheap and good at guessing who is ahead, but not Markov. This is "
                   "what depth-limited search uses at the horizon."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Drops discs into random columns.", 1, icon="dice"),
        Bot("carla", "Careful Carla", "Takes wins, blocks wins, never hands you one, "
            "likes the middle.", 2, cards=("win", "block", "no-gift", "middle"),
            icon="shield"),
        Bot("sam", "Shallow Sam", "Looks two plies ahead: his move and your reply.", 3,
            policy="policy_depth2", icon="eye"),
        Bot("dana", "Deep Dana", "Looks four plies ahead and scores the board by counting "
            "open lines.", 4, policy="policy_depth4", icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-carla", "Beat Careful Carla", "win", 1, bot="carla"),
        Challenge("tree", "Open the game-tree lens", "lens", 1, lens="tree"),
        Challenge("beat-sam", "Beat Shallow Sam", "win", 2, bot="sam"),
        Challenge("stack-carla", "Build a card stack that beats Careful Carla in 60% of "
                  "100 games", "sim", 3, bot="carla", metric="winrate", value=0.6),
    )

    # ------------------------------------------------------------- policies
    def policy_depth2(self) -> SearchPolicy:
        """Minimax two plies deep with the line-counting heuristic at the horizon."""
        return SearchPolicy(depth=2, name="depth 2")

    def policy_depth4(self) -> SearchPolicy:
        """Minimax four plies deep with the line-counting heuristic at the horizon."""
        return SearchPolicy(depth=4, name="depth 4")

    # ----------------------------------------------------------- rule cards
    def _gives_win_above(self, s: MNKState, a, player: int) -> bool:
        """After ``player`` drops in column ``a``, can the opponent win on the spot above?"""
        after = self.apply_action(s, a)
        if self.is_terminal(after) or after.board[a] is not None:
            return False        # the move ends the game, or the column is now full
        return self.wins_now(after, a, 1 - player)

    @avoid("no-gift", "Don't hand them a win",
           "Never drop where the spot above becomes a winning spot for the opponent.",
           "barrier")
    def card_no_gift(self, s, a, player):
        return self._gives_win_above(s, a, player)

    @pick("double", "Double threat",
          "Make two winning drops at once. They can only block one.", "fork")
    def card_double(self, s, candidates, player, rng):
        doubles = []
        for a in candidates:
            after = self.apply_action(s, a)
            if self.is_terminal(after):
                continue
            wins = [c for c in self.legal_actions(after) if self.wins_now(after, c, player)]
            if len(wins) >= 2:
                doubles.append(a)
        return rng.choice(doubles) if doubles else None

    @pick("middle", "Stay central",
          "Play the free column closest to the middle: central discs sit on the most lines.",
          "target")
    def card_middle(self, s, candidates, player, rng):
        mid = (self.cols - 1) / 2
        best = min(abs(c - mid) for c in candidates)
        return rng.choice([c for c in candidates if abs(c - mid) == best])
