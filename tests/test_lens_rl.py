"""The learn lens: value iteration, Q-learning, bandit algorithms."""

from __future__ import annotations

import json
import math
import time

import pytest

from strategy_lab.core import Seat, Session
from strategy_lab.core.match import play_out
from strategy_lab.core.policy import FunctionPolicy
from strategy_lab.families.mdp import DIRECTIONS
from strategy_lab.games.bandit import Bandit
from strategy_lab.games.cliff_walking import CliffWalking
from strategy_lab.games.frozen_lake import FrozenLake
from strategy_lab.games.nim import Nim
from strategy_lab.lenses import all_lenses, lenses_for
from strategy_lab.lenses.rl import RLLens, epsilon_greedy_entropy, moving_average, thin

lens = RLLens()


def session(g):
    sess = Session(g, [Seat("human")], 0)
    sess.advance()
    return sess


def success_rate(g, arrows, n=300, seed=11):
    """Simulate a greedy arrow policy on the real game rules; unknown cells move at random."""
    def act(game, s, player, rng):
        return arrows.get(str(s.pos)) or rng.choice(DIRECTIONS)

    wins = sum(1 for i in range(n)
               if g.outcome(play_out(g, [FunctionPolicy(act)], f"{seed}:{i}")[0], 0) == "win")
    return wins / n


def test_registered_and_applies_to_single_player_games_only():
    assert "rl" in all_lenses()
    for g in (FrozenLake(), CliffWalking(), Bandit()):
        assert lens.applies(g)
    assert not lens.applies(Nim())
    assert "rl" in [l.id for l in lenses_for(FrozenLake())]


def test_helpers():
    assert moving_average([1, 3, 5, 7], 2) == [1.0, 2.0, 4.0, 6.0]
    x, v = thin(list(range(1000)), 100)
    assert len(x) <= 101 and x[-1] == 1000 and v[-1] == 999
    assert thin([5.0, 6.0]) == ([1, 2], [5.0, 6.0])
    assert epsilon_greedy_entropy(4, 4, 0.0) == pytest.approx(2.0)
    assert epsilon_greedy_entropy(1, 4, 0.0) == 0.0
    assert epsilon_greedy_entropy(1, 4, 0.1) > 0


def test_value_iteration_policy_is_clearly_better_than_random_on_frozenlake():
    g = FrozenLake()
    r = lens.run(session(g), {"algorithm": "value-iteration"})
    assert r["algorithm"] == "value-iteration" and r["sweeps"] > 10
    assert r["curve"]["kind"] == "bellman-error" and r["curve"]["values"][-1] < 1e-6
    assert r["entropy"] is None
    assert r["policy"]["0"] in DIRECTIONS
    assert "5" not in r["policy"] and "15" not in r["policy"]           # hole and goal
    assert r["values"]["0"] > 0.4 and r["values"]["14"] > r["values"]["0"]
    greedy, wandering = success_rate(g, r["policy"]), success_rate(g, {})
    assert greedy > 0.5 and wandering < 0.1 and greedy > 10 * wandering
    assert r["evaluation"]["successRate"] > 0.5
    json.dumps(r)


def test_q_learning_on_the_cliff_learns_a_path_to_the_goal():
    g = CliffWalking()
    r = lens.run(session(g), {"algorithm": "q-learning", "episodes": 500})
    assert r["curve"]["kind"] == "return" and r["curve"]["average"][-1] > -60
    assert r["evaluation"]["successRate"] == 1.0
    assert r["evaluation"]["meanReturn"] >= -17.0
    assert success_rate(g, r["policy"], n=20) == 1.0
    assert r["values"][str(g.start)] > -20
    assert r["curve"]["average"][-1] > r["curve"]["average"][0]       # the average return rises


def test_policy_entropy_falls_from_two_bits_to_the_epsilon_floor():
    """With no reward found yet every action ties (2 bits); then epsilon-greedy takes over."""
    r = lens.run(session(FrozenLake(slippery=False)), {"algorithm": "q-learning",
                                                       "episodes": 400, "epsilon": 0.1})
    ent = r["entropy"]
    assert ent["max"] == pytest.approx(2.0)
    assert ent["values"][0] == pytest.approx(2.0)
    assert ent["values"][-1] == pytest.approx(epsilon_greedy_entropy(1, 4, 0.1), abs=0.05)


def test_overlay_shows_the_q_values_of_the_current_state():
    g = CliffWalking()
    r = lens.run(session(g), {"algorithm": "value-iteration", "gamma": 1.0})
    ov = r["overlay"]["actions"]
    assert set(ov) == set(DIRECTIONS)
    assert ov["up"]["tone"] == "best" and ov["up"]["value"] == pytest.approx(-13.0)
    assert ov["right"]["value"] < -100                        # straight into the cliff
    waiting = Session(FrozenLake(), [Seat("human")], 0, [{"p": 0, "a": "right"}])
    assert lens.run(waiting, {})["overlay"] == {"actions": {}}   # a chance node: no decision


def test_default_run_is_fast_and_reproducible():
    for g in (FrozenLake(), FrozenLake(size="8x8"), CliffWalking(slippery=True), Bandit()):
        start = time.perf_counter()
        a = lens.run(session(g), {})
        assert time.perf_counter() - start < 0.5, g.id
        assert a == lens.run(session(g), {})
        json.dumps(a)


def test_seed_changes_the_run():
    g = FrozenLake()
    a = lens.run(session(g), {"seed": 1})
    b = lens.run(session(g), {"seed": 2})
    assert a["curve"]["values"] != b["curve"]["values"]


def test_algorithm_not_for_this_game_falls_back_to_a_default():
    assert lens.run(session(FrozenLake()), {"algorithm": "ucb"})["algorithm"] == "q-learning"
    assert lens.run(session(Bandit()), {"algorithm": "value-iteration"})["algorithm"] == "ucb"
    assert lens.run(session(Bandit()), {})["algorithms"] == ["epsilon-greedy", "ucb", "softmax"]


# ----------------------------------------------------------------- bandits
def test_ucb_regret_is_below_what_a_random_player_suffers():
    r = lens.run(session(Bandit()), {"algorithm": "ucb", "episodes": 1000})
    assert r["kind"] == "bandit" and r["practice"] is True
    final = r["regret"]["values"][-1]
    assert final < 0.5 * r["regret"]["baseline"]
    assert r["regret"]["values"] == sorted(r["regret"]["values"])       # regret never shrinks


def test_all_bandit_algorithms_beat_random_regret():
    g = Bandit()
    for alg in ("epsilon-greedy", "ucb", "softmax"):
        r = lens.run(session(g), {"algorithm": alg, "episodes": 1000})
        assert r["regret"]["values"][-1] < r["regret"]["baseline"], alg


def test_bandit_estimates_and_entropy_curves():
    r = lens.run(session(Bandit()), {"algorithm": "ucb", "episodes": 800})
    assert len(r["estimates"]["arms"]) == 5
    assert r["entropy"]["max"] == pytest.approx(math.log2(5))
    assert r["entropy"]["values"][0] > 1.0 and r["entropy"]["values"][-1] < 0.3
    soft = lens.run(session(Bandit()), {"algorithm": "softmax", "episodes": 800})
    assert all(0.0 <= v <= math.log2(5) for v in soft["entropy"]["values"])


def test_lens_never_reveals_the_odds_of_a_game_in_progress():
    sess = session(Bandit())
    r = lens.run(sess, {})
    assert r["practice"] and r["regret"]["probs"] is None and r["regret"]["best"] is None
    assert "probs" not in {k for k in r if k != "regret"}


def test_after_the_last_pull_the_real_arms_and_your_regret_appear():
    g = Bandit(arms=3, pulls=5)
    sess = Session(g, [Seat("human")], 4)
    sess.advance()
    while not sess.terminal:
        sess.act(0)
        sess.advance()
    r = lens.run(sess, {"episodes": 200})
    assert r["practice"] is False
    assert r["regret"]["probs"] == list(sess.state.probs)
    best = max(sess.state.probs)
    assert r["regret"]["best"] == sess.state.probs.index(best)
    assert r["you"]["regret"] == pytest.approx(5 * (best - sess.state.probs[0]), abs=1e-3)
    assert r["you"]["reward"] == sess.state.total


def test_options_fit_the_game():
    def named(game):
        return {o["name"]: o for o in lens.meta(game)["options"]}

    grid, bandit = named(FrozenLake()), named(Bandit())
    assert grid["algorithm"]["choices"] == ["auto", "value-iteration", "q-learning"]
    assert bandit["algorithm"]["choices"] == ["auto", "epsilon-greedy", "ucb", "softmax"]
    assert grid["temperature"]["hidden"] and not grid["alpha"].get("hidden")
    assert bandit["alpha"]["hidden"] and bandit["episodes"]["label"] == "Pulls"
