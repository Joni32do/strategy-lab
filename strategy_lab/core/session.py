"""Sessions: one game being played, rebuilt from its action log.

A session is fully described by ``(game id, params, seed, seats, log)``.
The log lists every action in order, chance outcomes included, as
``{"p": player, "a": action}``. Replaying the log reproduces the position
exactly, so the server keeps no state between requests: the browser sends
the log, the server replays it, applies the new action, lets bots and
chance move, and returns the new log.

This is what makes the development loop pleasant: edit a game's Python
file, the dev server restarts, and the next request replays your current
game under the new rules. If a logged action became illegal, the replay
stops there and reports it (:attr:`Session.replay_error`) instead of
failing.

Bots and chance draw from ``random.Random(f"{seed}:{step}:{salt}")``, so a
given seed always produces the same game for the same human moves.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from strategy_lab.core.game import CHANCE, TERMINAL, Action, Game
from strategy_lab.core.policy import Policy


class ReplayError(ValueError):
    """A logged action does not fit the position it is applied to."""


@dataclass
class Seat:
    """Who sits in a seat: ``kind`` is ``"human"`` or ``"bot"``.

    A bot plays the persona ``bot`` (a :class:`~strategy_lab.core.game.Bot`
    id), or, if ``cards`` is given, that card stack.
    """

    kind: str = "bot"
    bot: str = "random"
    cards: list[str] | None = None

    @classmethod
    def from_json(cls, d: dict) -> "Seat":
        return cls(kind=d.get("kind", "bot"), bot=d.get("bot") or "random",
                   cards=d.get("cards"))

    def to_json(self) -> dict:
        d: dict[str, Any] = {"kind": self.kind}
        if self.kind == "bot":
            d["bot"] = self.bot
            if self.cards is not None:
                d["cards"] = list(self.cards)
        return d


def _normalize(a: Any) -> Action:
    """JSON gives back ints as ints and strings as strings; reject the rest."""
    if isinstance(a, bool) or not isinstance(a, (int, str)):
        raise ReplayError(f"actions must be int or str, got {a!r}")
    return a


@dataclass
class Step:
    """One applied log entry with its caption (for the move log)."""

    player: int
    action: Action
    text: str
    chance: dict | None = None
    label: str = ""
    #: Seats that may see this step (``None``: everyone).
    private: tuple[int, ...] | None = None
    hidden_text: str = ""

    def to_json(self, index: int, viewer: int | None = None) -> dict:
        """JSON for the move log as seen by ``viewer`` (``None``: spectator sees all)."""
        if self.private is not None and viewer is not None and viewer not in self.private:
            return {"i": index, "p": self.player, "text": self.hidden_text, "hidden": True}
        d = {"i": index, "p": self.player, "a": self.action, "text": self.text,
             "label": self.label}
        if self.chance:
            d["chance"] = self.chance
        return d


class Session:
    """A game in progress. See the module docstring."""

    def __init__(self, game: Game, seats: list[Seat], seed: int = 0,
                 log: list[dict] | None = None, strict: bool = False):
        if len(seats) != game.num_players:
            raise ValueError(f"{game.id} needs {game.num_players} seats, got {len(seats)}")
        self.game = game
        self.seats = seats
        self.seed = int(seed)
        self.state = game.initial_state()
        self.steps: list[Step] = []
        self.timeout = False
        #: Why the replay stopped early, or ``None`` if the whole log applied.
        self.replay_error: str | None = None
        self._policies: dict[int, Policy] = {}
        for entry in log or []:
            try:
                self._apply(int(entry["p"]), _normalize(entry["a"]))
            except (ReplayError, KeyError, TypeError, ValueError) as e:
                if strict:
                    raise
                self.replay_error = f"replay stopped at step {len(self.steps) + 1}: {e}"
                break

    # ------------------------------------------------------------------ query
    @property
    def log(self) -> list[dict]:
        return [{"p": st.player, "a": st.action} for st in self.steps]

    @property
    def terminal(self) -> bool:
        return self.timeout or self.game.is_terminal(self.state)

    def to_move(self) -> int:
        """Seat to move, :data:`CHANCE`, or :data:`TERMINAL`."""
        if self.terminal:
            return TERMINAL
        return self.game.current_player(self.state)

    def human_seats(self) -> list[int]:
        return [i for i, s in enumerate(self.seats) if s.kind == "human"]

    def waiting_for_human(self) -> bool:
        p = self.to_move()
        return p >= 0 and self.seats[p].kind == "human"

    def returns(self) -> list[float]:
        if self.timeout:
            return list(self.game.timeout_returns(self.state))
        if self.game.is_terminal(self.state):
            return list(self.game.returns(self.state))
        return [0.0] * self.game.num_players

    def rng(self, salt: str = "") -> random.Random:
        return random.Random(f"{self.seed}:{len(self.steps)}:{salt}")

    def policy(self, seat: int) -> Policy:
        if seat not in self._policies:
            st = self.seats[seat]
            self._policies[seat] = self.game.make_policy(st.bot, cards=st.cards)
        return self._policies[seat]

    # ------------------------------------------------------------------ change
    def _apply(self, player: int, action: Action, check: bool = True) -> None:
        g, s = self.game, self.state
        if self.terminal:
            raise ReplayError("the game is already over")
        cur = g.current_player(s)
        if player != cur:
            raise ReplayError(f"expected player {cur} to move, log says {player}")
        info = None
        if cur == CHANCE:
            try:
                outcomes = [o for o, _ in g.chance_outcomes(s)]
            except NotImplementedError:
                outcomes = None
            if check and outcomes is not None and action not in outcomes:
                raise ReplayError(f"{action!r} is not a possible chance outcome")
            text = g.describe_chance(s, action)
            info = g.chance_info(s, action) if outcomes is not None else None
        else:
            if check and action not in g.legal_actions(s):
                raise ReplayError(f"{action!r} is not legal for player {cur}")
            text = g.describe(s, action, cur)
        label = g.action_label(s, action)
        private = g.privacy(s, action, cur)
        hidden = g.describe_hidden(s, action, cur) if private is not None else ""
        self.state = g.apply_action(s, action)
        self.steps.append(Step(cur, action, text, info, label, private, hidden))
        if len(self.steps) >= g.max_steps and not g.is_terminal(self.state):
            self.timeout = True

    def act(self, action: Action) -> None:
        """Apply a human action. Raises :class:`ReplayError` if not allowed."""
        action = _normalize(action)
        p = self.to_move()
        if p < 0 or self.seats[p].kind != "human":
            raise ReplayError("it is not a human's turn")
        self._apply(p, action)

    def step(self) -> bool:
        """Let chance or a bot make one move. False if a human must act or it is over."""
        p = self.to_move()
        if p == TERMINAL:
            return False
        if p == CHANCE:
            a = self.game.sample_chance(self.state, self.rng("chance"))
        elif self.seats[p].kind == "bot":
            legal = self.game.legal_actions(self.state)
            if len(legal) == 1:
                a = legal[0]
            else:
                a = self.policy(p).act(self.game, self.state, p, self.rng("bot"))
        else:
            return False
        self._apply(p, a)
        return True

    def advance(self, limit: int | None = None) -> int:
        """Run :meth:`step` until a human must act (or ``limit`` steps). Returns count."""
        n = 0
        while (limit is None or n < limit) and self.step():
            n += 1
        return n

    def undo(self) -> None:
        """Rewind to before the last human action (and what followed it)."""
        humans = set(self.human_seats())
        cut = None
        for i in range(len(self.steps) - 1, -1, -1):
            if self.steps[i].player in humans:
                cut = i
                break
        if cut is None:
            return
        keep = self.log[:cut]
        fresh = Session(self.game, self.seats, self.seed, keep)
        self.__dict__.update(fresh.__dict__)
