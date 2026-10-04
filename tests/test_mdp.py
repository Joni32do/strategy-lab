"""The single-agent family: the RL toolkit, grid-world rules and the planning model."""

from __future__ import annotations

import json
import random

import pytest

from strategy_lab.core import CHANCE
from strategy_lab.core.match import simulate
from strategy_lab.families.mdp import (
    DIRECTIONS, GridWorld, SinglePlayerGame, entropy_bits, epsilon_greedy_probs,
    greedy_actions, greedy_probs, perpendicular, softmax_probs, value_iteration,
)
from strategy_lab.games.cliff_walking import CliffWalking
from strategy_lab.games.frozen_lake import FrozenLake


def test_toolkit_functions():
    assert greedy_actions([1.0, 3.0, 3.0]) == [1, 2]
    assert greedy_actions({"a": 1.0, "b": 2.0}) == ["b"]
    assert greedy_probs([0.0, 1.0, 1.0]) == [0.0, 0.5, 0.5]
    probs = epsilon_greedy_probs([0.0, 1.0, 0.0, 0.0], 0.2)
    assert probs[1] == pytest.approx(0.05 + 0.8) and sum(probs) == pytest.approx(1.0)
    cold, hot = softmax_probs([0.0, 1.0], 0.1), softmax_probs([0.0, 1.0], 100.0)
    assert cold[1] > 0.99 and abs(hot[1] - 0.5) < 0.01
    assert entropy_bits([0.25] * 4) == pytest.approx(2.0) and entropy_bits([1.0, 0.0]) == 0.0
    assert perpendicular("up") == ("left", "right")


def test_value_iteration_on_a_two_state_chain():
    model = {0: {"go": [(1.0, 1, 0.0, False)]},
             1: {"go": [(1.0, 1, 1.0, True)]}}
    plan = value_iteration(model, gamma=0.9)
    assert plan.values[1] == pytest.approx(1.0) and plan.values[0] == pytest.approx(0.9)
    assert plan.best_actions(0) == ["go"] and plan.deltas[-1] < 1e-7


def test_lineage_and_family():
    assert FrozenLake.lineage() == ["Game", "SinglePlayerGame", "GridWorld", "FrozenLake"]
    assert FrozenLake.family()["id"] == "gridworld"
    assert issubclass(CliffWalking, GridWorld) and CliffWalking.num_players == 1


def test_a_slippery_move_is_a_decision_then_a_chance_node():
    g = FrozenLake()
    s = g.apply_action(g.initial_state(), "right")
    assert g.current_player(s) == CHANCE and s.pending == "right"
    outcomes = dict(g.chance_outcomes(s))
    assert outcomes == pytest.approx({"up": 1 / 3, "right": 1 / 3, "down": 1 / 3})
    nxt = g.apply_action(s, "down")
    assert nxt.pos == 4 and nxt.steps == 1 and g.current_player(nxt) == 0
    assert "slips" in g.describe_chance(s, "down") and "as intended" in g.describe_chance(s, "right")


def test_a_dry_map_has_no_chance_nodes():
    g = FrozenLake(slippery=False)
    s = g.apply_action(g.initial_state(), "right")
    assert g.current_player(s) == 0 and s.pos == 1 and not g.stochastic


def test_holes_goals_walls_and_edges():
    g = FrozenLake(slippery=False)
    s = g.initial_state()
    assert g.apply_action(s, "up").pos == 0 and g.apply_action(s, "left").pos == 0   # edge
    hole = g.apply_action(g.apply_action(s, "right"), "down")
    assert g.is_terminal(hole) and g.returns(hole) == [0.0]
    goal = g.initial_state()
    goal.pos = 14
    goal = g.apply_action(goal, "right")
    assert g.is_terminal(goal) and g.returns(goal) == [1.0]


def test_step_limit_ends_the_game():
    g = FrozenLake(slippery=False, limit=2)
    s = g.apply_action(g.apply_action(g.initial_state(), "up"), "up")
    assert g.is_terminal(s) and "Out of steps" in g.status(s, 0)
    assert FrozenLake().step_limit == 100 and FrozenLake(size="8x8").step_limit == 200


def test_default_transitions_agree_with_the_tabular_model():
    """The generic chance-enumerating model equals the grid world's hand-built one."""
    g = FrozenLake()
    s = g.initial_state()
    for a in DIRECTIONS:
        generic = {}
        for p, ns, r in SinglePlayerGame.transitions(g, s, a):
            generic[(ns.pos, r)] = generic.get((ns.pos, r), 0.0) + p
        table = {(nxt, r): p for p, nxt, r, _ in g.model[s.pos][a]}
        assert generic == pytest.approx(table)
        assert sum(p for p, _, _ in g.transitions(s, a)) == pytest.approx(1.0)


def test_states_are_the_decision_cells():
    g = FrozenLake()
    assert len(g.states()) == 16 - 5                    # minus 4 holes and the goal
    assert len(CliffWalking().states()) == 37


def test_scene_puts_moves_on_neighbor_cells_and_the_agent_on_its_tile():
    g = FrozenLake(slippery=False)
    s = g.initial_state()
    part = g.scene(s, 0)["parts"][0]
    assert part["style"] == "tiles" and part["rows"] == 4
    assert part["cells"][0]["pieces"][0]["shape"] == "agent"
    assert part["cells"][1]["action"] == "right" and part["cells"][4]["action"] == "down"
    assert part["cells"][5]["tone"] == "hole" and part["cells"][15]["tone"] == "goal"
    json.dumps(g.scene(s, 0))
    pending = FrozenLake().apply_action(FrozenLake().initial_state(), "right")
    assert all("action" not in c for c in FrozenLake().scene(pending, 0)["parts"][0]["cells"])


def test_cards():
    g = FrozenLake(slippery=False)
    s = g.initial_state()
    rng = random.Random(0)
    assert g.card("goal").fn(g, s, list(DIRECTIONS), 0, rng) in ("right", "down")
    assert g.card("safe").fn(g, s, "right", 0) is False
    near_hole = g.initial_state()
    near_hole.pos = 1
    assert g.card("safe").fn(g, near_hole, "down", 0) is True           # (1,1) is a hole
    assert g.card("bump").fn(g, s, "up", 0) is True and g.card("bump").fn(g, s, "down", 0) is False
    assert g.card("plan").fn(g, s, list(DIRECTIONS), 0, rng) in DIRECTIONS


def test_bad_maps_are_rejected():
    class Broken(GridWorld):
        id = "broken"
        layout = ("S.", ".")
    with pytest.raises(ValueError):
        Broken()


def test_planning_beats_wandering_by_simulation():
    g = FrozenLake()
    plan = g.make_policy(cards=["plan"])
    random_policy = g.make_policy("randy")
    best = simulate(g, [plan], n=200, seed=1).mean_return(0)
    worst = simulate(g, [random_policy], n=200, seed=1).mean_return(0)
    assert best > 0.55 and worst < 0.1
