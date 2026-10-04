"""Rule tests for the Qwixx gym env (server/qwixx_env.py).

Covers the parts of the published rules that are easy to get wrong: the
right-of-your-last-cross constraint, the five-cross gate on the 12/2, the
lock's bonus cross, simultaneous locking on one white sum, penalties, and
both end conditions. Then plays whole episodes through gymnasium.make to
prove the env behaves for a random policy.

Run: uv run python server/test_qwixx.py
"""
import random

import gymnasium as gym
import numpy as np

import qwixx_env as Q
from qwixx_env import ENV_ID, AGENT, LAST_COL, N_COLS, N_ROWS, PASS, Sheet, col_of, tri, value_at


def act(row, col):
    return row * N_COLS + col


def test_geometry():
    assert [value_at(0, c) for c in range(N_COLS)] == list(range(2, 13))
    assert [value_at(2, c) for c in range(N_COLS)] == list(range(12, 1, -1))
    for row in range(N_ROWS):
        for col in range(N_COLS):
            assert col_of(row, value_at(row, col)) == col
    assert col_of(0, 13) == -1 and col_of(2, 1) == -1
    assert Q.ACTION_NAMES[act(0, 0)] == "red 2"
    assert Q.ACTION_NAMES[act(3, 0)] == "blue 12"
    assert Q.ACTION_NAMES[PASS] == "pass"
    print("ok  geometry: red/yellow ascend, green/blue descend, names line up")


def test_scoring_and_lock_gate():
    s = Sheet()
    unlocked = [False] * N_ROWS
    # crosses must move strictly right
    assert s.can_mark(0, 4, unlocked)
    s.mark(0, 4)
    assert not s.can_mark(0, 4, unlocked) and not s.can_mark(0, 3, unlocked)
    assert s.can_mark(0, 5, unlocked)
    # the 12 needs five crosses first
    for col in (5, 6, 7):
        s.mark(0, col)
    assert s.counts[0] == 4 and not s.can_mark(0, LAST_COL, unlocked)
    s.mark(0, 8)
    assert s.counts[0] == 5 and s.can_mark(0, LAST_COL, unlocked)
    # ...and locking scores one extra cross: 6 marks -> 7 crosses -> 28
    s.mark(0, LAST_COL)
    assert s.counts[0] == 6 and s.crosses(0) == 7
    assert tri(7) == 28 and s.score() == 28
    # a locked row is closed to everyone
    assert not s.can_mark(1, 3, [False, True, False, False])
    # penalties cost 5 each
    s.penalties = 2
    assert s.score() == 28 - 10
    print("ok  scoring: right-only, five-cross gate, lock bonus (6 marks = 28), -5 penalties")


def test_full_row():
    s = Sheet()
    for col in range(N_COLS):
        assert s.can_mark(0, col, [False] * N_ROWS)
        s.mark(0, col)
    assert s.crosses(0) == 12 and s.score() == 78
    print("ok  scoring: a complete row is 11 marks + lock = 12 crosses = 78 points")


def _fresh(**kw):
    env = Q.QwixxEnv(render_mode="ansi", **kw)
    env.reset(seed=1)
    return env


def test_simultaneous_lock():
    """Several players may lock the same row on one white sum - each
    still needing their own five crosses."""
    env = _fresh()
    env.locked = [False] * N_ROWS
    for seat in range(4):
        for col in range(5):
            env.sheets[seat].mark(0, col)          # everyone holds five reds
    env.sheets[3] = Sheet()                        # ...except P3, who holds none
    env.dice = [6, 6, 1, 1, 1, 1]                  # white sum 12 = red's last cell
    env.active = AGENT
    env.phase = "white"
    env.turn_marked = False

    assert env.action_mask()[act(0, LAST_COL)] == 1, "agent has 5 reds: red 12 is legal"
    env._do_white((0, LAST_COL))

    assert env.locked[0], "red is locked once the 12 is crossed"
    assert env.sheets[AGENT].marks[0][LAST_COL], "agent got the lock"
    assert env.sheets[1].marks[0][LAST_COL], "P1 locked the same row in the same roll"
    assert env.sheets[2].marks[0][LAST_COL], "P2 locked the same row in the same roll"
    assert not env.sheets[3].marks[0][LAST_COL], "P3 had no five crosses - no lock for them"
    assert env.sheets[AGENT].crosses(0) == 7 and env.sheets[AGENT].score() == 28
    print("ok  lock: simultaneous on one white sum, still gated on five crosses per player")


def test_locked_row_is_closed_afterwards():
    env = _fresh()
    env.locked = [True, False, False, False]
    env.dice = [3, 4, 5, 5, 5, 5]                  # white sum 7 exists in every row
    env.phase = "white"
    assert env.action_mask()[act(0, col_of(0, 7))] == 0, "red is locked"
    assert env.action_mask()[act(1, col_of(1, 7))] == 1, "yellow is open"
    env.phase = "color"
    env.active = AGENT
    assert all(r != 0 for r, _ in env.agent_options()), "the red die left the game"
    print("ok  lock: a locked row is closed to white sums and colour combos alike")


def test_penalty_and_pass():
    """Passing is free off-turn and costs the active player a penalty."""
    env = _fresh()
    env.active = 1                                  # not the agent's turn
    env.phase = "white"
    env.dice = [3, 4, 1, 1, 1, 1]
    before = [s.penalties for s in env.sheets]
    env._do_white(None)
    assert env.sheets[AGENT].penalties == before[AGENT], "off-turn pass is free"

    env = _fresh()
    env.active = AGENT
    env.phase = "white"
    env.turn_marked = False
    env.dice = [3, 4, 1, 1, 1, 1]
    env._do_white(None)
    assert env.phase == "color"
    env._do_color(None)
    assert env.sheets[AGENT].penalties == 1, "active player marking nothing takes a penalty"
    assert env.sheets[AGENT].score() == -5
    print("ok  penalty: free for non-active players, -5 for an active player who marks nothing")


def test_end_conditions():
    env = _fresh()
    env.locked = [True, True, False, False]
    env._check_end()
    assert env.terminated, "two locked rows end the game"

    env = _fresh()
    env.sheets[2].penalties = 4
    env._check_end()
    assert env.terminated, "a fourth penalty ends the game"
    print("ok  end: two locked rows, or anybody's fourth penalty")


def test_obs_modes():
    for mode in Q.OBS_MODES:
        env = Q.QwixxEnv(obs_mode=mode)
        obs, info = env.reset(seed=3)
        assert obs.shape == (Q.obs_size(mode),) == env.observation_space.shape
        assert obs.dtype == np.float32
        assert env.observation_space.contains(obs), (mode, obs.min(), obs.max())
        assert set(info) >= {"action_mask", "phase", "scores", "legal"}
    print("ok  obs: counts/sheet/table sizes %s match their spaces and stay in [0,1]"
          % [Q.obs_size(m) for m in Q.OBS_MODES])


def test_mask_matches_options():
    env = _fresh()
    rng = random.Random(4)
    for _ in range(400):
        if env.terminated:
            env.reset(seed=rng.randrange(1000))
        mask = env.action_mask()
        legal = {act(r, c) for r, c in env.agent_options()} | {PASS}
        assert {a for a in range(Q.N_ACTIONS) if mask[a]} == legal
        assert env.agent_options(), "the env only suspends on real decisions"
        env.step(rng.choice(sorted(legal)))
    print("ok  mask: exactly the legal crosses plus pass, and every step is a real choice")


def test_illegal_action_is_a_noop():
    env = _fresh()
    mask = env.action_mask()
    illegal = next(a for a in range(Q.N_ACTIONS) if not mask[a])
    snapshot = env._render_ansi()
    obs, reward, term, trunc, info = env.step(illegal)
    assert info.get("illegal") is True and reward == 0.0 and not term and not trunc
    assert env._render_ansi() == snapshot, "an illegal click must not move the game"
    print("ok  illegal action: rejected as a no-op, game state untouched")


def test_reward_modes():
    """score mode telescopes to the final score; margin mode pays at the end."""
    env = Q.QwixxEnv(reward_mode="score")
    env.reset(seed=9)
    rng = random.Random(9)
    total = 0.0
    for _ in range(500):
        mask = env.action_mask()
        a = rng.choice([i for i in range(Q.N_ACTIONS) if mask[i]])
        _obs, reward, term, _tr, _info = env.step(a)
        total += reward
        if term:
            break
    assert term, "episode should end well inside 500 steps"
    assert abs(total - env.sheets[AGENT].score()) < 1e-6, (total, env.sheets[AGENT].score())

    env = Q.QwixxEnv(reward_mode="margin")
    env.reset(seed=9)
    rng = random.Random(9)
    payouts = []
    for _ in range(500):
        mask = env.action_mask()
        a = rng.choice([i for i in range(Q.N_ACTIONS) if mask[i]])
        _obs, reward, term, _tr, _info = env.step(a)
        payouts.append(reward)
        if term:
            break
    scores = [s.score() for s in env.sheets]
    assert all(p == 0.0 for p in payouts[:-1]), "margin pays only at the end"
    assert abs(payouts[-1] - (scores[AGENT] - max(scores[1:]))) < 1e-6
    print("ok  reward: score mode returns the final score (%d), margin pays the gap (%+d)"
          % (env.sheets[AGENT].score(), payouts[-1]))


def test_episodes_through_make():
    """The registered env, driven the way the server drives it."""
    env = gym.make(ENV_ID, render_mode="ansi")
    assert env.action_space.n == 45
    lengths, scores, reasons = [], [], {"locks": 0, "penalties": 0}
    for seed in range(20):
        _obs, _info = env.reset(seed=seed)
        assert isinstance(env.render(), str) and "QWIXX" in env.render()
        steps, term, trunc = 0, False, False
        while not (term or trunc) and steps < 600:
            a = int(env.action_space.sample(mask=env.unwrapped.action_mask()))
            _obs, _r, term, trunc, _info = env.step(a)
            steps += 1
        assert term and not trunc, "a Qwixx game always ends on its own"
        raw = env.unwrapped
        assert sum(raw.locked) >= 2 or any(s.penalties >= 4 for s in raw.sheets)
        reasons["locks" if sum(raw.locked) >= 2 else "penalties"] += 1
        lengths.append(steps)
        scores.append(raw.sheets[AGENT].score())
        assert "GAME OVER" in env.render()
    env.close()
    print("ok  episodes: 20 random-legal games end on their own, %d-%d steps, scores %d..%d, %s"
          % (min(lengths), max(lengths), min(scores), max(scores), reasons))


def test_seeding_is_reproducible():
    def run(seed):
        env = Q.QwixxEnv()
        env.reset(seed=seed)
        rng = random.Random(0)
        out = []
        while not env.terminated:
            mask = env.action_mask()
            a = rng.choice([i for i in range(Q.N_ACTIONS) if mask[i]])
            env.step(a)
            out.append(tuple(s.score() for s in env.sheets))
        return out

    assert run(42) == run(42), "same seed, same game"
    assert run(42) != run(43), "different seed, different game"
    print("ok  seeding: reset(seed=...) reproduces a game exactly")


def test_render_is_readable():
    env = _fresh()
    text = env._render_ansi()
    for row in Q.ROW_NAMES:
        assert row in text
    assert "dice:" in text and "your sheet" in text and "your call" in text
    assert "P1 " in text and "P3 " in text
    print("ok  render: sheet, dice, opponents and the legal options are all in the ansi view")
    print()
    print(text)


if __name__ == "__main__":
    test_geometry()
    test_scoring_and_lock_gate()
    test_full_row()
    test_simultaneous_lock()
    test_locked_row_is_closed_afterwards()
    test_penalty_and_pass()
    test_end_conditions()
    test_obs_modes()
    test_mask_matches_options()
    test_illegal_action_is_a_noop()
    test_reward_modes()
    test_episodes_through_make()
    test_seeding_is_reproducible()
    test_render_is_readable()
    print("\nALL PASSED")
