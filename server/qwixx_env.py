"""Qwixx as a Gymnasium environment - the lab's own roll-and-write game.

Every other gym entry in the catalog comes from the vendored Gymnasium
submodule. This one is ours, registered into the same registry under the
"strategy_lab" namespace so it flows through the existing play path
(server/envs.py -> /api/env/new|step|reset -> js/env-play.js) with no
special cases: Discrete actions, an ansi render, a seedable reset.

THE GAME (4 players, published Gamewright rules)
  Four color-rows on every player's sheet: red and yellow run 2..12,
  green and blue run 12..2. Crosses in a row must always move to the
  RIGHT of your rightmost cross - skipped numbers are gone for good.
  The active player rolls 6 dice (2 white + one per color). Then:
    white phase  every player may cross the sum of the two white dice
                 in one row of their choice (nobody is forced to),
    color phase  the active player may additionally combine ONE white
                 die with ONE colored die and cross that number in the
                 matching color-row.
  The active player who marks nothing in either phase takes a penalty
  (-5 points, four of them and the game is over).
  To cross a row's rightmost number (12 / 2) you must already hold at
  least 5 crosses in that row; doing so also crosses the lock symbol,
  which counts as one further cross, and closes the row for everyone.
  Several players may lock the same row in the same roll (the white
  sum is simultaneous) but not afterwards - each still needs their own
  five crosses.
  The game ends the moment two rows are locked or somebody marks their
  fourth penalty. A row with n crosses (the lock counts as one) scores
  n*(n+1)/2; penalties cost 5 each.

THE MDP (see the catalog entry in js/gym-games.js)
  Gymnasium is single-agent, so seat 0 is the agent and seats 1..3 are
  scripted bots. The bots are deliberately simple and legible: each has
  a skip tolerance and takes the cheapest cross that skips no more
  numbers than that, always grabs a lock, and dodges its own fourth
  penalty when a legal cross exists.

  action  Discrete(45): 44 = (row, column) marks, 44 itself = pass.
          One mark per step; the env carries the phase, so an active
          player's turn is up to two steps (white, then color). Phases
          in which the agent has no legal cross are skipped - every
          observation you are handed is a real decision. `action_mask()`
          exposes legality (server/envs.py samples random policies
          through it, so "policy: random" plays legal Qwixx).
  obs     Box in [0,1]. Three obs_modes, which are exactly the three
          candidate state spaces in the catalog panel:
            "counts" (19)  per-row cross COUNTS + dice: NOT Markov, the
                           frontier is lost so legality is unknowable,
            "sheet"  (59)  your full sheet + dice: Markov for your own
                           scoring, blind to the three sheets that
                           decide when rows lock and the game ends,
            "table" (194)  all four sheets + dice + phase: Markov.
  reward  reward_mode="score" (default): the change in your own Qwixx
          score each step, so the episode return IS your final score.
          reward_mode="margin": 0 until the end, then your score minus
          the best opponent's.

Run tests: uv run python server/test_qwixx.py
"""

import gymnasium as gym
import numpy as np
from gymnasium import spaces

ENV_ID = "strategy_lab/Qwixx-v0"

N_ROWS, N_COLS = 4, 11
ROW_NAMES = ("red", "yellow", "green", "blue")
ASCENDING = (True, True, False, False)     # red/yellow 2..12, green/blue 12..2
LAST_COL = N_COLS - 1                      # the 12 / 2 that locks the row

PASS = N_ROWS * N_COLS                     # action 44
N_ACTIONS = PASS + 1

N_PLAYERS = 4
AGENT = 0
LOCK_MIN = 5                               # crosses needed before the 12 / 2
MAX_PENALTIES = 4
PENALTY_COST = 5
LOCKS_TO_END = 2

# Feature-block sizes, single-sourced so observation_space and _obs()
# cannot drift apart.
_SHEET_FEATS = N_ROWS * N_COLS + 1         # 44 marks + penalties
_DICE_FEATS = 3 + N_ROWS                   # 2 white + their sum + 4 colored
_FLAG_FEATS = 3                            # phase, is-active, marked-this-turn
OBS_MODES = ("counts", "sheet", "table")
REWARD_MODES = ("score", "margin")


def value_at(row, col):
    """The number printed in this cell (red/yellow ascend, green/blue descend)."""
    return 2 + col if ASCENDING[row] else 12 - col


def col_of(row, value):
    """Column holding `value` in `row`, or -1 if the row has no such number."""
    col = value - 2 if ASCENDING[row] else 12 - value
    return col if 0 <= col < N_COLS else -1


def tri(n):
    """The Qwixx score for n crosses in one row: (n^2 + n) / 2."""
    return n * (n + 1) // 2


ACTION_NAMES = [
    "%s %d" % (ROW_NAMES[r], value_at(r, c))
    for r in range(N_ROWS) for c in range(N_COLS)
] + ["pass"]


def obs_size(obs_mode):
    base = N_ROWS + _DICE_FEATS + _FLAG_FEATS          # locks + dice + flags
    if obs_mode == "counts":
        return base + N_ROWS + 1                       # per-row counts + penalties
    if obs_mode == "sheet":
        return base + _SHEET_FEATS
    return base + N_PLAYERS * _SHEET_FEATS


class Sheet:
    """One player's score sheet."""

    __slots__ = ("marks", "last", "counts", "penalties")

    def __init__(self):
        self.marks = [[False] * N_COLS for _ in range(N_ROWS)]
        self.last = [-1] * N_ROWS          # rightmost crossed column, -1 = none
        self.counts = [0] * N_ROWS
        self.penalties = 0

    def can_mark(self, row, col, locked):
        """Legality of one cross, against the given lock state.

        `locked` is passed in rather than read from the game so the white
        phase can be resolved simultaneously: every player is judged
        against the locks as they stood when the dice were rolled.
        """
        if col < 0 or col >= N_COLS or locked[row]:
            return False
        if col <= self.last[row]:                      # must move right
            return False
        if col == LAST_COL and self.counts[row] < LOCK_MIN:
            return False                               # the five-cross rule
        return True

    def mark(self, row, col):
        self.marks[row][col] = True
        self.last[row] = col
        self.counts[row] += 1

    def crosses(self, row):
        """Crosses counting the lock symbol, which scores as one more."""
        return self.counts[row] + (1 if self.marks[row][LAST_COL] else 0)

    def score(self):
        return (sum(tri(self.crosses(r)) for r in range(N_ROWS))
                - PENALTY_COST * self.penalties)


class QwixxEnv(gym.Env):
    """4-player Qwixx from seat 0's chair; seats 1..3 are scripted bots."""

    metadata = {"render_modes": ["ansi"], "name": "Qwixx"}

    def __init__(self, render_mode=None, obs_mode="table", reward_mode="score",
                 opponent_skips=(2, 1, 3)):
        if obs_mode not in OBS_MODES:
            raise ValueError("obs_mode must be one of %s" % (OBS_MODES,))
        if reward_mode not in REWARD_MODES:
            raise ValueError("reward_mode must be one of %s" % (REWARD_MODES,))
        if len(opponent_skips) != N_PLAYERS - 1:
            raise ValueError("need one skip tolerance per opponent seat")
        self.render_mode = render_mode
        self.obs_mode = obs_mode
        self.reward_mode = reward_mode
        # seat -> how many numbers a bot will skip over for a cross
        self.skips = [None] + [int(s) for s in opponent_skips]

        self.action_space = spaces.Discrete(N_ACTIONS)
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(obs_size(obs_mode),), dtype=np.float32)
        self.action_names = list(ACTION_NAMES)   # picked up by server/envs.py

        self.sheets = [Sheet() for _ in range(N_PLAYERS)]
        self.locked = [False] * N_ROWS
        self.dice = [0] * (2 + N_ROWS)
        self.active = AGENT
        self.turn = 0
        self.turn_marked = False
        self.phase = "roll"
        self.terminated = False

    # ------------------------------------------------------------------ #
    # gym API
    # ------------------------------------------------------------------ #
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.sheets = [Sheet() for _ in range(N_PLAYERS)]
        self.locked = [False] * N_ROWS
        self.dice = [0] * (2 + N_ROWS)
        self.active = AGENT                    # the agent opens the game
        self.turn = 0
        self.turn_marked = False
        self.phase = "roll"
        self.terminated = False
        self._advance()
        return self._obs(), self._info()

    def step(self, action):
        action = int(action)
        if self.terminated:
            return self._obs(), 0.0, True, False, self._info()

        if not self.action_mask()[action]:
            # An in-range but illegal cross leaves the game untouched: a
            # misclick in the browser must not silently cost a penalty.
            info = self._info()
            info["illegal"] = True
            return self._obs(), 0.0, False, False, info

        before = self.sheets[AGENT].score()
        choice = None if action == PASS else (action // N_COLS, action % N_COLS)
        if self.phase == "white":
            self._do_white(choice)
        else:
            self._do_color(choice)
        self._advance()

        if self.reward_mode == "margin":
            reward = self._margin() if self.terminated else 0.0
        else:
            reward = float(self.sheets[AGENT].score() - before)
        return self._obs(), reward, self.terminated, False, self._info()

    def render(self):
        if self.render_mode == "ansi":
            return self._render_ansi()
        return None

    # ------------------------------------------------------------------ #
    # legality
    # ------------------------------------------------------------------ #
    def action_mask(self):
        """int8 vector over the 45 actions; pass is always available."""
        mask = np.zeros(N_ACTIONS, dtype=np.int8)
        mask[PASS] = 1
        if not self.terminated:
            for row, col in self.agent_options():
                mask[row * N_COLS + col] = 1
        return mask

    def agent_options(self):
        """The crosses the agent may take at this exact decision point."""
        if self.terminated:
            return []
        if self.phase == "white":
            return self._white_options(AGENT, self.locked)
        if self.phase == "color" and self.active == AGENT:
            return self._color_options(AGENT, self.locked)
        return []

    def _white_options(self, seat, locked):
        total = self.dice[0] + self.dice[1]
        out = []
        for row in range(N_ROWS):
            col = col_of(row, total)
            if self.sheets[seat].can_mark(row, col, locked):
                out.append((row, col))
        return out

    def _color_options(self, seat, locked):
        out = []
        for row in range(N_ROWS):
            if locked[row]:
                continue                       # that die has left the game
            for white in (self.dice[0], self.dice[1]):
                col = col_of(row, white + self.dice[2 + row])
                if (row, col) not in out and self.sheets[seat].can_mark(row, col, locked):
                    out.append((row, col))
        return out

    # ------------------------------------------------------------------ #
    # game flow
    # ------------------------------------------------------------------ #
    def _advance(self):
        """Play on until the agent faces a real choice, or the game ends."""
        while not self.terminated:
            if self.phase == "roll":
                self._roll()
                continue
            if self.phase == "white":
                if self._white_options(AGENT, self.locked):
                    return                     # suspend: the agent chooses
                self._do_white(None)
                continue
            # colour phase - only the active player acts
            if self.active == AGENT:
                if self._color_options(AGENT, self.locked):
                    return                     # suspend: the agent chooses
                self._do_color(None)
            else:
                self._do_color(self._bot_color(self.active))

    def _roll(self):
        self.dice = [int(self.np_random.integers(1, 7)) for _ in range(2 + N_ROWS)]
        for row in range(N_ROWS):
            if self.locked[row]:
                self.dice[2 + row] = 0         # removed from the game
        self.turn_marked = False
        self.phase = "white"

    def _do_white(self, agent_choice):
        """Resolve the white sum for all four players simultaneously."""
        pre = list(self.locked)                # everyone is judged against this
        picks = {AGENT: agent_choice}
        for seat in range(1, N_PLAYERS):
            picks[seat] = self._bot_white(seat, pre)
        for seat, pick in picks.items():
            if pick is None:
                continue
            self.sheets[seat].mark(*pick)
            if seat == self.active:
                self.turn_marked = True
        self._update_locks()
        self.phase = "color"
        self._check_end()

    def _do_color(self, choice):
        if choice is not None:
            self.sheets[self.active].mark(*choice)
            self.turn_marked = True
            self._update_locks()
        self._end_turn()

    def _update_locks(self):
        for row in range(N_ROWS):
            if not self.locked[row] and any(s.marks[row][LAST_COL] for s in self.sheets):
                self.locked[row] = True

    def _end_turn(self):
        if not self.turn_marked:
            self.sheets[self.active].penalties += 1
        self._check_end()
        if self.terminated:
            return
        self.active = (self.active + 1) % N_PLAYERS
        self.turn += 1
        self.phase = "roll"

    def _check_end(self):
        if (sum(self.locked) >= LOCKS_TO_END
                or any(s.penalties >= MAX_PENALTIES for s in self.sheets)):
            self.terminated = True

    def _margin(self):
        mine = self.sheets[AGENT].score()
        return float(mine - max(self.sheets[p].score() for p in range(1, N_PLAYERS)))

    # ------------------------------------------------------------------ #
    # the bots
    # ------------------------------------------------------------------ #
    def _bot_pick(self, seat, options, max_skip):
        """Cheapest cross this bot will accept, or None to pass.

        Cost is how many numbers the cross burns; a lock is always worth
        taking, whatever it costs.
        """
        if not options:
            return None
        sheet = self.sheets[seat]
        cost = lambda m: m[1] - sheet.last[m[0]] - 1          # noqa: E731
        locks = [m for m in options if m[1] == LAST_COL]
        if locks:
            return min(locks, key=cost)
        best = min(options, key=lambda m: (cost(m), -sheet.counts[m[0]], m[0]))
        return best if cost(best) <= max_skip else None

    def _bot_white(self, seat, locked):
        return self._bot_pick(seat, self._white_options(seat, locked), self.skips[seat])

    def _bot_color(self, seat):
        options = self._color_options(seat, self.locked)
        # Last chance to avoid a penalty, so the bar drops; and it will
        # never hand itself a game-ending fourth penalty while a legal
        # cross is on the table.
        max_skip = self.skips[seat] + (0 if self.turn_marked else 2)
        pick = self._bot_pick(seat, options, max_skip)
        if (pick is None and not self.turn_marked and options
                and self.sheets[seat].penalties == MAX_PENALTIES - 1):
            pick = self._bot_pick(seat, options, N_COLS)
        return pick

    # ------------------------------------------------------------------ #
    # observation / info
    # ------------------------------------------------------------------ #
    def _sheet_vec(self, seat):
        sheet = self.sheets[seat]
        v = [1.0 if m else 0.0 for row in sheet.marks for m in row]
        v.append(sheet.penalties / MAX_PENALTIES)
        return v

    def _obs(self):
        v = []
        if self.obs_mode == "counts":
            # Counts only: how many crosses per row, not WHICH - so the
            # frontier, and with it legality, is unrecoverable.
            v += [self.sheets[AGENT].counts[r] / N_COLS for r in range(N_ROWS)]
            v.append(self.sheets[AGENT].penalties / MAX_PENALTIES)
        elif self.obs_mode == "sheet":
            v += self._sheet_vec(AGENT)
        else:
            v += [x for seat in range(N_PLAYERS) for x in self._sheet_vec(seat)]
        v += [1.0 if l else 0.0 for l in self.locked]
        v += [self.dice[0] / 6.0, self.dice[1] / 6.0,
              (self.dice[0] + self.dice[1]) / 12.0]
        v += [self.dice[2 + r] / 6.0 for r in range(N_ROWS)]
        v += [1.0 if self.phase == "color" else 0.0,
              1.0 if self.active == AGENT else 0.0,
              1.0 if self.turn_marked else 0.0]
        return np.asarray(v, dtype=np.float32)

    def _info(self):
        mask = self.action_mask()
        return {
            "action_mask": mask,
            "phase": self.phase,
            "active": self.active,
            "turn": self.turn,
            "locked": list(self.locked),
            "scores": [s.score() for s in self.sheets],
            "legal": [ACTION_NAMES[a] for a in range(N_ACTIONS) if mask[a]],
        }

    # ------------------------------------------------------------------ #
    # ansi render (this is what you actually play in the browser)
    # ------------------------------------------------------------------ #
    def _cell(self, seat, row, col):
        sheet = self.sheets[seat]
        if sheet.marks[row][col]:
            return "X"
        if col <= sheet.last[row] or self.locked[row]:
            return "."                          # skipped past or locked out: gone
        return str(value_at(row, col))

    def _row_line(self, row):
        cells = "".join("%4s" % self._cell(AGENT, row, c) for c in range(N_COLS))
        sheet = self.sheets[AGENT]
        lock = "[X]" if sheet.marks[row][LAST_COL] else ("[#]" if self.locked[row] else "[ ]")
        return " %-7s%s  %s %5d %5d" % (
            ROW_NAMES[row], cells, lock, sheet.crosses(row), tri(sheet.crosses(row)))

    def _dice_line(self):
        white = "white %d + %d = %d" % (self.dice[0], self.dice[1],
                                        self.dice[0] + self.dice[1])
        colors = "  ".join(
            "%s %s" % (ROW_NAMES[r], "-" if self.locked[r] else self.dice[2 + r])
            for r in range(N_ROWS))
        return " dice: %-22s|  %s" % (white, colors)

    def _options_line(self):
        if self.terminated:
            return ""
        options = ", ".join("%s %d" % (ROW_NAMES[r], value_at(r, c))
                            for r, c in self.agent_options())
        if self.phase == "white":
            if self.active != AGENT:
                return " your call (white sum): %s, or pass for free." % options
            return " your call (white sum): %s, or pass (the colour die follows)." % options
        cost = "" if self.turn_marked else " -> costs a penalty"
        return " your call (white + colour): %s, or pass%s." % (options, cost)

    def _render_ansi(self):
        who = "you" if self.active == AGENT else "P%d" % self.active
        head = " QWIXX  turn %d  |  %s to act  |  phase: %s" % (
            self.turn + 1, who, "white sum" if self.phase == "white" else "white + colour")
        lines = [head, self._dice_line(), ""]
        # column stops match _row_line: lock ends at 57, n at 63, pts at 69
        lines.append(" your sheet".ljust(53) + "lock" + "n".rjust(6) + "pts".rjust(6))
        lines += [self._row_line(r) for r in range(N_ROWS)]
        lines.append(" X crossed   . out of reach   [X] you locked the row"
                     "   [#] locked by somebody else")
        sheet = self.sheets[AGENT]
        lines.append(" penalties %s   score %d" % (
            "".join("X" if i < sheet.penalties else "." for i in range(MAX_PENALTIES)),
            sheet.score()))
        lines.append("")
        for seat in range(1, N_PLAYERS):
            other = self.sheets[seat]
            counts = "  ".join("%s %d" % (ROW_NAMES[r][0], other.crosses(r))
                               for r in range(N_ROWS))
            lines.append(" P%d  %s   pen %d   score %3d   (skips up to %d)" % (
                seat, counts, other.penalties, other.score(), self.skips[seat]))
        lines.append("")
        if self.terminated:
            scores = [s.score() for s in self.sheets]
            best = max(scores)
            winners = [i for i, s in enumerate(scores) if s == best]
            why = ("two rows locked" if sum(self.locked) >= LOCKS_TO_END
                   else "somebody took a fourth penalty")
            lines.append(" GAME OVER (%s)  -  scores: %s" % (
                why, "  ".join("%s %d" % ("you" if i == AGENT else "P%d" % i, s)
                               for i, s in enumerate(scores))))
            lines.append(" winner: %s" % ", ".join(
                "you" if w == AGENT else "P%d" % w for w in winners))
        else:
            lines.append(self._options_line())
        return "\n".join(lines)


if ENV_ID not in gym.registry:
    gym.register(id=ENV_ID, entry_point=QwixxEnv, max_episode_steps=500)
