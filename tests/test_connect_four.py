"""Connect Four: gravity, cards, and the search bots."""

from __future__ import annotations

import random

from strategy_lab.core import SearchPolicy
from strategy_lab.core.match import simulate
from strategy_lab.families.board import MNKState
from strategy_lab.games.connect_four import ConnectFour

ROWS, COLS = 6, 7


def play(g, actions):
    s = g.initial_state()
    for a in actions:
        s = g.apply_action(s, a)
    return s


def board_from(cells: dict[tuple[int, int], int], to_move: int = 0) -> MNKState:
    """A position from ``{(row, col): seat}``, row 0 at the top."""
    board = [None] * (ROWS * COLS)
    for (r, c), seat in cells.items():
        board[r * COLS + c] = seat
    return MNKState(board, to_move, None, (), len(cells))


def test_discs_fall_to_the_lowest_free_cell():
    g = ConnectFour()
    s = play(g, [3, 3, 3])
    assert [i for i, v in enumerate(s.board) if v is not None] == [24, 31, 38]
    assert g.landing(s, 3) == 17
    full = play(g, [0, 0, 0, 0, 0, 0])
    assert 0 not in g.legal_actions(full) and len(g.legal_actions(full)) == 6


def test_four_in_every_direction_wins():
    g = ConnectFour()
    assert g.winner(play(g, [0, 6, 1, 6, 2, 6, 3])) == 0                    # row
    assert g.winner(play(g, [0, 1, 0, 1, 0, 1, 0])) == 0                    # column
    assert g.winner(play(g, [0, 1, 1, 2, 2, 3, 2, 3, 3, 6, 3])) == 0        # diagonal
    assert g.winner(play(g, [0, 1, 2, 3])) is None


def test_metadata_and_inheritance():
    assert ConnectFour.lineage() == ["Game", "MNKGame", "ConnectFour"]
    assert (ConnectFour.rows, ConnectFour.cols, ConnectFour.k) == (6, 7, 4)
    assert ConnectFour.seat_names == ("Red", "Yellow")
    ids = [c.id for c in ConnectFour.cards()]
    assert ids[:3] == ["win", "block", "center"]
    assert {"no-gift", "double", "middle"} <= set(ids)


def test_opening_has_four_classes_under_the_mirror():
    g = ConnectFour()
    s = g.initial_state()
    classes = g.action_classes(s, g.legal_actions(s))
    assert [len(c) for c in classes] == [2, 2, 2, 1]


def test_no_gift_vetoes_a_drop_that_lets_the_opponent_win_above():
    g = ConnectFour()
    # Yellow holds row 4, columns 0-2. If red drops in column 3 (landing on the
    # bottom row) yellow completes four on the cell above.
    s = board_from({(5, 0): 0, (5, 1): 1, (5, 2): 0,
                    (4, 0): 1, (4, 1): 1, (4, 2): 1}, to_move=0)
    card = g.card("no-gift")
    assert card.fn(g, s, 3, 0) is True
    assert card.fn(g, s, 4, 0) is False
    assert card.fn(g, s, 0, 0) is False


def test_double_threat_makes_two_winning_drops():
    g = ConnectFour()
    s = board_from({(5, 2): 0, (5, 3): 0, (5, 6): 1, (4, 6): 1}, to_move=0)
    pick = g.card("double").fn(g, s, g.legal_actions(s), 0, random.Random(0))
    assert pick in (1, 4)
    assert g.card("double").fn(g, g.initial_state(), list(range(7)), 0, random.Random(0)) is None


def test_stay_central_prefers_the_middle_columns():
    g = ConnectFour()
    s = g.initial_state()
    assert g.card("middle").fn(g, s, [0, 1, 5, 6], 0, random.Random(0)) in (1, 5)
    assert g.card("middle").fn(g, s, list(range(7)), 0, random.Random(0)) == 3


def test_search_bots_use_the_inherited_heuristic_with_the_right_depth():
    g = ConnectFour()
    sam, dana = g.make_policy("sam"), g.make_policy("dana")
    assert isinstance(sam, SearchPolicy) and sam.depth == 2
    assert isinstance(dana, SearchPolicy) and dana.depth == 4
    assert g.heuristic(g.initial_state(), 0) == 0


def test_depth_two_takes_a_win_and_blocks_one():
    g = ConnectFour()
    sam = g.make_policy("sam")
    win = board_from({(5, 0): 0, (5, 1): 0, (5, 2): 0, (5, 6): 1, (4, 6): 1}, to_move=0)
    assert sam.act(g, win, 0, random.Random(1)) == 3
    block = board_from({(5, 3): 0, (4, 3): 0, (3, 3): 0, (5, 0): 1, (5, 1): 1}, to_move=1)
    assert sam.act(g, block, 1, random.Random(1)) == 3


def test_stronger_players_beat_weaker_ones():
    g = ConnectFour()
    sam, randy = g.make_policy("sam"), g.make_policy("randy")
    assert simulate(g, [sam, randy], n=20, seed=1).wins(0) == 20
    carla = g.make_policy("carla")
    assert simulate(g, [carla, randy], n=20, seed=1).wins(0) >= 19
    stack = g.make_policy(cards=["win", "block", "no-gift", "double", "center", "middle"])
    res = simulate(g, [stack, carla], n=60, seed=2)
    assert res.wins(0) > res.wins(1) * 1.5               # the full stack out-plays Carla
