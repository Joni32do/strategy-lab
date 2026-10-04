"""Tic-Tac-Toe and the k-in-a-row family: rules, symmetry, solver, cards."""

from __future__ import annotations

from strategy_lab.core import SearchPolicy, Solver
from strategy_lab.core.match import simulate
from strategy_lab.games.tictactoe import TicTacToe


def play(g, actions):
    s = g.initial_state()
    for a in actions:
        s = g.apply_action(s, a)
    return s


def test_rows_columns_diagonals_win():
    g = TicTacToe()
    assert g.winner(play(g, [0, 3, 1, 4, 2])) == 0          # top row
    assert g.winner(play(g, [1, 0, 2, 4, 3, 8])) == 1       # diagonal for O
    s = play(g, [0, 1, 2, 4, 3, 5, 7, 6, 8])                # full board, no line
    assert g.is_terminal(s) and g.winner(s) is None


def test_symmetry_folds_opening_to_three_classes():
    g = TicTacToe()
    s = g.initial_state()
    classes = g.action_classes(s, g.legal_actions(s))
    assert sorted(len(c) for c in classes) == [1, 4, 4]     # center, corners, edges


def test_canonical_key_reaches_765_positions():
    g = TicTacToe()
    seen_raw, seen_canon = set(), set()
    frontier = [g.initial_state()]
    while frontier:
        s = frontier.pop()
        k = g.key(s)
        if k in seen_raw:
            continue
        seen_raw.add(k)
        seen_canon.add(g.canonical_key(s))
        if not g.is_terminal(s):
            frontier.extend(g.apply_action(s, a) for a in g.legal_actions(s))
    assert len(seen_raw) == 5478
    assert len(seen_canon) == 765


def test_solver_says_draw_and_center_is_not_better_than_corner():
    g = TicTacToe()
    solver = Solver(g)
    s = g.initial_state()
    assert solver.value(s) == 0
    values = dict(solver.action_values(s))
    assert values[4] == values[0] == values[1] == 0


def test_perfect_card_stack_never_loses():
    g = TicTacToe()
    minnie = g.make_policy("minnie")
    for bot in ("randy", "gus", "carla", "minnie"):
        res = simulate(g, [minnie, g.make_policy(bot)], n=60, seed=1)
        assert res.wins(1) == 0, f"Minnie lost to {bot}"
    res = simulate(g, [minnie, SearchPolicy()], n=20, seed=2)
    assert res.draws() == 20


def test_inherited_cards_come_first():
    ids = [c.id for c in TicTacToe.cards()]
    assert ids[:3] == ["win", "block", "center"]
    assert "fork" in ids and "smother" in ids
    assert TicTacToe.lineage() == ["Game", "MNKGame", "TicTacToe"]
    assert TicTacToe.family()["id"] == "k-in-a-row"
