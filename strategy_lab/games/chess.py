"""Chess on the OpenSpiel engine.

The rules (move generation, castling, en passant, promotion, check, mate and
the draw rules) come from ``pyspiel``'s chess. This file adds what the lab
needs on top: an 8x8 board scene, a material heuristic for depth-limited
search, a handful of rule cards, and the bots.

Board scene
-----------
A ``scene.grid`` of 8x8 cells in ``checker`` style with ``coords`` on. Row 0
is rank 8, column 0 is file a (cell index ``8 * (7 - rank) + file``). Pieces
are ``scene.piece(owner, "glyph", glyph=letter)`` with the FEN letter
(uppercase is White, seat 0).

Limitation: a cell holds one ``action`` but a chess move needs a start *and*
a target square. For version 1 every legal move therefore stays in the
generic action bar (SAN labels such as ``Nf3``). The board highlights the
last move (tone ``last``) and a king in check (tone ``bad``). Cells that hold
a movable piece also carry one extra key, ``moves``, for views that want
click-to-move::

    cell["moves"] = [{"to": <cell index>, "action": <action>, "label": "Nf3"}, ...]

A view may show the targets of the clicked piece and send the matching
action (a promotion lists four entries with the same ``to``). Views that
ignore ``moves`` still work through the action bar.
"""

from __future__ import annotations

import math
from functools import lru_cache

import pyspiel
from pyspiel import chess as spiel_chess

from strategy_lab.core import Bot, Challenge, Model, Rulebook, SearchPolicy, pick, avoid, scene
from strategy_lab.core.game import Action
from strategy_lab.families.external import SpielGame

#: Piece values in pawns. The king is priceless and never counted.
PIECE_VALUE = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0}
NAMES = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}


@lru_cache(maxsize=4096)
def parse_fen(fen: str) -> tuple[tuple[str, ...], bool]:
    """Return ``(squares, white_to_move)``; ``squares`` has 64 entries, row 0 = rank 8.

    Empty squares are ``""``, pieces are their FEN letter.
    """
    placement, side = fen.split()[:2]
    squares: list[str] = []
    for rank in placement.split("/"):
        for ch in rank:
            squares.extend([""] * int(ch) if ch.isdigit() else [ch])
    return tuple(squares), side == "w"


def square_index(file: int, rank: int) -> int:
    """Grid cell of a square: file 0..7 (a..h), rank 0..7 (1..8)."""
    return 8 * (7 - rank) + file


def square_name(cell: int) -> str:
    return "abcdefgh"[cell % 8] + str(8 - cell // 8)


def material(squares: tuple[str, ...], white: bool) -> int:
    """Material (in pawns) of one side."""
    return sum(PIECE_VALUE[ch.lower()] for ch in squares if ch and ch.isupper() == white)


class Chess(SpielGame):
    id = "chess"
    name = "Chess"
    icon = "chess"
    tagline = "Perfect information, a tree no computer can finish. Where do you stop looking?"
    chapter = "trees"
    order = 40
    concepts = ("game-tree", "branching-factor", "heuristic", "minimax", "markov-property",
                "monte-carlo", "mcts")
    spiel_name = "chess"
    seat_names = ("White", "Black")
    #: OpenSpiel numbers Black 0 and White 1. The lab wants the first mover in seat 0.
    engine_seats = (1, 0)
    #: A game that runs this long ends as a draw (the engine's own cap is 17695).
    max_steps = 400
    #: The conformance suite plays every bot on both sides; keep that fast.
    conformance_steps = 40

    rulebook = Rulebook(
        summary="The classic two-player board game. White moves first.",
        steps=(
            ("The goal", "Checkmate the opposing king: attack it so that it cannot escape "
                         "capture on the next move. Stalemate (no legal move, but not in "
                         "check) and several other conditions are draws."),
            ("The pieces", "Each side has a king, a queen, two rooks, two bishops, two "
                           "knights and eight pawns, each moving in its own way. A pawn "
                           "that reaches the far rank promotes."),
            ("Special rules", "Castling, en passant capture and the repetition and "
                              "fifty-move draws depend on history that the board alone "
                              "does not show. That is what the models below are about."),
            ("Moving here", "Pick a move from the list under the board (standard algebraic "
                            "notation: Nf3 is a knight to f3, x is a capture, + is check, "
                            "# is mate). The board marks the last move."),
        ),
        extra=(
            ("Forced draws", "OpenSpiel ends the game at once after three repetitions and "
                             "after 100 reversible plies (the fifty-move rule). Its source "
                             "says of the latter: \"This is theoretically a draw that needs "
                             "to be claimed, but we implement it as a forced draw for now.\" "
                             "(open_spiel/games/chess/chess.cc)"),
            ("Move cap", "A game that lasts 400 plies is scored as a draw."),
        ),
        source="https://handbook.fide.com/chapter/E012023",
    )

    models = (
        Model("board-only", "Board + side to move", False,
              state="the 8x8 piece placement plus whose turn it is",
              size="about 10^43 reachable positions",
              actions="legal moves from the board alone (about 35 on average, up to 218)",
              transition="your move lands, then the opponent replies: from your seat the "
                         "opponent is part of the environment",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="the naive encoding: cheap to store, but you cannot generate castling "
                   "or en passant moves, and you cannot detect a repetition draw, without "
                   "more than the board."),
        Model("fen", "FEN (board + rights + ep + clock)", "approx",
              state="board + side to move + castling rights + en-passant square + "
                    "halfmove clock",
              size="still about 10^43",
              actions="legal moves (about 35 on average, up to 218)",
              transition="same as above, now with the rights that make every move legal",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="Markov for check, checkmate and the fifty-move rule, but threefold "
                   "repetition still needs to know which earlier positions recurred. FEN "
                   "alone cannot see that."),
        Model("fen-history", "FEN + position history", True,
              state="FEN plus the set of positions reached since the last irreversible "
                    "move (pawn move or capture)",
              size="FEN times a position list that resets at every capture or pawn move",
              actions="legal moves (about 35 on average, up to 218). OpenSpiel and "
                      "AlphaZero encode a fixed space of 4672 actions",
              transition="same as above, plus the list of positions seen",
              reward="+1 win / 0 draw / -1 loss at the end; gamma = 1",
              note="what engines actually track: fully Markov, including repetition "
                   "claims, at the cost of a position list that grows until the next "
                   "capture or pawn move resets it."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Plays a random legal move. Hangs his queen for fun.",
            1, icon="dice"),
        Bot("greta", "Grabby Greta", "Mates in one if she sees it, otherwise takes the "
            "juiciest piece. No plan, no defense.", 2, cards=("mate", "capture"),
            icon="hand"),
        Bot("monte", "Monte", "Plays 30 random games from each position and picks the "
            "move that did best. Finds mate in one, not much else.", 2,
            policy="monte_policy", icon="dice"),
        Bot("sven", "Safe-Step Sven", "Never leaves a piece hanging, grabs free material, "
            "checks when nothing else is going on.", 3,
            cards=("mate", "safe", "capture", "castle", "promote", "check"), icon="shield"),
        Bot("maxine", "Material Maxine", "Looks two plies ahead and counts pawns. She "
            "trades up and never blunders into a mate in one.", 4,
            policy="maxine_policy", icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("tree", "Open the game-tree lens", "lens", 1, lens="tree"),
        Challenge("beat-greta", "Beat Grabby Greta", "win", 1, bot="greta"),
        Challenge("beat-sven", "Beat Safe-Step Sven", "win", 2, bot="sven"),
        Challenge("beat-maxine", "Beat Material Maxine", "win", 3, bot="maxine"),
    )

    # ------------------------------------------------------------------ board
    def squares(self, s: pyspiel.State) -> tuple[str, ...]:
        return parse_fen(str(s))[0]

    def white_to_move(self, s: pyspiel.State) -> bool:
        return parse_fen(str(s))[1]

    def decode(self, s: pyspiel.State, a: Action):
        """The engine's ``Move`` for action ``a``: ``from_square`` and ``to_square``."""
        return spiel_chess.action_to_move(int(a), s.board())

    def last_move(self, s: pyspiel.State) -> tuple[int, int, str] | None:
        """``(from cell, to cell, SAN)`` of the last ply, or ``None`` at the start."""
        history = s.history()
        if not history:
            return None
        before = s.clone()
        mover = 1 - (len(history) - 1) % 2          # engine id: White (even plies) is 1
        before.undo_action(mover, history[-1])
        move = self.decode(before, history[-1])
        origin, target = move.from_square, move.to_square
        return (square_index(origin.x, origin.y), square_index(target.x, target.y),
                before.action_to_string(mover, history[-1]))

    def in_check(self, s: pyspiel.State) -> bool:
        last = self.last_move(s)
        return bool(last) and last[2].endswith(("+", "#"))

    # ----------------------------------------------------------------- search
    def heuristic(self, s: pyspiel.State, player: int) -> float:
        """Material balance of ``player`` in pawns, squashed to ``(-1, 1)``."""
        squares = self.squares(s)
        diff = material(squares, player == 0) - material(squares, player != 0)
        return math.tanh(diff / 6)

    def monte_policy(self):
        return self.mcts(30, name="Monte", worlds=1)

    def maxine_policy(self):
        return SearchPolicy(depth=2, name="Material Maxine")

    # ------------------------------------------------------------- rule cards
    def _san(self, s: pyspiel.State, a: Action) -> str:
        return s.action_to_string(s.current_player(), int(a))

    def _capture_value(self, s: pyspiel.State, a: Action) -> int | None:
        """Value of the piece taken by ``a`` (``None`` if it is no capture)."""
        if "x" not in self._san(s, a):
            return None
        target = self.decode(s, a).to_square
        taken = self.squares(s)[square_index(target.x, target.y)]
        return PIECE_VALUE[taken.lower()] if taken else 1       # en passant takes a pawn

    def _mover_value(self, s: pyspiel.State, a: Action) -> int:
        origin = self.decode(s, a).from_square
        return PIECE_VALUE[self.squares(s)[square_index(origin.x, origin.y)].lower()]

    @pick("mate", "Mate in one", "If a move checkmates, play it.", "crown")
    def card_mate(self, s, candidates, player, rng):
        return next((a for a in candidates if self._san(s, a).endswith("#")), None)

    @pick("capture", "Take the best piece",
          "Capture the most valuable piece you can, with the cheapest piece you have.",
          "sword")
    def card_capture(self, s, candidates, player, rng):
        best, best_score = None, -99
        for a in candidates:
            gain = self._capture_value(s, a)
            if gain is None:
                continue
            score = 10 * gain - self._mover_value(s, a)
            if score > best_score:
                best, best_score = a, score
        return best

    @pick("check", "Give check", "A check forces a reply. Play one if nothing better is on.",
          "bolt")
    def card_check(self, s, candidates, player, rng):
        checks = [a for a in candidates if "+" in self._san(s, a)]
        return rng.choice(checks) if checks else None

    @pick("castle", "Castle", "Tuck the king away and wake up a rook.", "castle")
    def card_castle(self, s, candidates, player, rng):
        return next((a for a in candidates if self._san(s, a).startswith("O-O")), None)

    @pick("promote", "Promote to a queen", "A pawn on the last rank becomes a queen.",
          "star")
    def card_promote(self, s, candidates, player, rng):
        return next((a for a in candidates if "=Q" in self._san(s, a)), None)

    @avoid("safe", "Do not hang pieces",
           "Skip a move that leaves the moved piece where the opponent can take it for "
           "free (it is worth more than what it captured).", "shield")
    def card_safe(self, s, a, player):
        if self._mover_value(s, a) <= (self._capture_value(s, a) or 0):
            return False                      # an even or better trade is fine
        target = self.decode(s, a).to_square
        cell = square_index(target.x, target.y)
        after = s.clone()
        after.apply_action(int(a))
        for b in after.legal_actions():
            if "x" in after.action_to_string(after.current_player(), b):
                landing = self.decode(after, b).to_square
                if square_index(landing.x, landing.y) == cell:
                    return True
        return False

    # ----------------------------------------------------------- presentation
    def status(self, s, viewer) -> str:
        if self.is_terminal(s):
            last = self.last_move(s)
            mated = bool(last) and last[2].endswith("#")
            base = super().status(s, viewer)
            return f"Checkmate. {base}" if mated else base
        base = super().status(s, viewer)
        side = self.seat_label(self.current_player(s))
        text = f"{base} ({side})" if viewer is not None and viewer == self.current_player(s) else base
        return f"Check! {text}" if self.in_check(s) else text

    def scene(self, s: pyspiel.State, viewer):
        squares, white = parse_fen(str(s))
        terminal = self.is_terminal(s)
        last = self.last_move(s)
        check = last is not None and last[2].endswith(("+", "#"))
        king_cell = None
        if check:
            king = "k" if white else "K"
            king_cell = next((i for i, ch in enumerate(squares) if ch == king), None)
        movable: dict[int, list[dict]] = {}
        if not terminal and (viewer is None or viewer == self.current_player(s)):
            for a in self.legal_actions(s):
                m = self.decode(s, a)
                origin = square_index(m.from_square.x, m.from_square.y)
                movable.setdefault(origin, []).append({
                    "to": square_index(m.to_square.x, m.to_square.y), "action": a,
                    "label": self._san(s, a)})
        cells = []
        for i, ch in enumerate(squares):
            pieces = [scene.piece(0 if ch.isupper() else 1, "glyph", glyph=ch)] if ch else []
            tone = "last" if last and i in last[:2] else ""
            if i == king_cell:
                tone = "bad"
            cell = scene.cell(pieces=pieces, tone=tone)
            if i in movable:
                cell["moves"] = movable[i]
            cells.append(cell)
        board = scene.grid(8, 8, cells, style="checker", coords=True)
        sides = (True, False)
        players = [scene.player(self.seat_label(seat), sub=f"material {material(squares, sides[seat])}",
                                active=not terminal and (white == sides[seat]), owner=seat)
                   for seat in (0, 1)]
        return scene.scene([board], players=players, status=self.status(s, viewer))
