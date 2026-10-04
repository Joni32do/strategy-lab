"""The tree lens: how good is each move, and how big is the game tree?

For a two-player game without chance and without hidden information, every
position has a value: win, draw or loss with best play on both sides. This
lens looks at the position on the board and answers three questions.

1. **What is each move worth?** Exact minimax with a transposition table
   (:class:`~strategy_lab.core.search.Solver`) if the tree fits the node
   budget. Positions that are the same up to symmetry are solved once.
2. **What if the tree is too big?** Depth-limited alpha-beta search with the
   game's heuristic at the horizon, if the game has one. Values are then
   guesses in ``(-1, 1)``, not facts.
3. **No heuristic either?** The lens says "too big" and estimates the size
   from random playouts: an average branching factor ``b`` and game length
   ``d`` give about ``b^d`` lines of play.

All values are from the point of view of the **player to move**.

Options: ``budget`` (positions the exact solver may store), ``depth`` (plies
of the heuristic search).

Result schema::

    {
      "mode":    "exact" | "heuristic" | "estimate" | "terminal",
      "mover":   <seat to move>, "moverName": "X",
      "value":   null | <float>,           # best value for the mover
      "text":    "Win" | "Draw" | "Loss" | "+0.42" | "too big" | "game over",
      "outcome": null | "win" | "draw" | "loss",   # exact mode only
      "tooBig":  <bool>,
      "actions": [{"a", "label", "value", "text", "best", "exact"}],
      "best":    [<best actions>],
      "overlay": {"actions": {"<action>": {"text", "tone", "value"}}},
      "symmetry": {"moves": 9, "decisions": 3,
                   "classes": [{"members": [<actions>], "labels": [...],
                                "value", "text", "best"}]},
      "stats":   {"searched": <positions created>, "distinct": <canonical positions
                  stored, exact mode only>, "branching": <average legal moves>,
                  "depth": <plies>, "seconds": <float>},
      "pv":      ["label", ...],           # principal variation
      "tree":    {"label": "root", "value", "text",
                  "children": [{"a", "label", "size": <moves in the class>, "value",
                                "text", "best",
                                "children": [{"a", "label", "size", "value", "text",
                                              "best"}],
                                "more": <replies left out>}],
                  "more": 0},
      "estimate": null | {"branching", "length", "log10Size", "text"}
    }

Values in ``tree`` are from the root mover's point of view; ``best`` at the
second level marks the reply that is best for the opponent (the lowest value).
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Callable

from strategy_lab.core.game import CHANCE, Game
from strategy_lab.core.search import Solver, TooBig, alphabeta
from strategy_lab.lenses.base import Lens

EPS = 1e-9


class Probe:
    """Wraps a game and counts the work a search does.

    Search code only calls rule methods, so a wrapper that forwards
    everything and counts ``apply_action`` and ``legal_actions`` measures
    positions created and the average branching factor without touching the
    solver. An optional deadline raises :class:`TooBig` for slow engines.
    """

    def __init__(self, game: Game, deadline: float | None = None):
        self._game = game
        self.deadline = deadline
        self.nodes = 0
        self.expansions = 0
        self.moves = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._game, name)

    def apply_action(self, s, a):
        self.nodes += 1
        if self.deadline is not None and time.perf_counter() > self.deadline:
            raise TooBig("out of time")
        return self._game.apply_action(s, a)

    def legal_actions(self, s):
        actions = self._game.legal_actions(s)
        self.expansions += 1
        self.moves += len(actions)
        return actions

    @property
    def branching(self) -> float:
        return self.moves / self.expansions if self.expansions else 0.0


def estimate_size(game: Game, s, playouts: int = 24, seed: int = 0) -> dict:
    """Estimate ``b^d`` from random playouts starting at ``s``.

    Returns ``{"branching", "length", "log10Size", "text"}``.
    """
    rng = random.Random(seed)
    moves = positions = steps = 0
    for _ in range(playouts):
        state = game.copy_state(s)
        n = 0
        while not game.is_terminal(state) and n < 1000:
            if game.current_player(state) == CHANCE:
                a = game.sample_chance(state, rng)
            else:
                legal = game.legal_actions(state)
                moves += len(legal)
                positions += 1
                a = rng.choice(legal)
            state = game.apply_action(state, a)
            n += 1
        steps += n
    b = moves / positions if positions else 1.0
    d = steps / playouts
    log10 = d * math.log10(b) if b > 1 else 0.0
    return {"branching": round(b, 2), "length": round(d, 1), "log10Size": round(log10, 1),
            "text": f"about 10^{round(log10)} lines of play ({b:.1f} moves, {d:.0f} plies)"}


def exact_text(value: float) -> str:
    """Win, draw or loss from the sign of an exact value."""
    if value > EPS:
        return "Win"
    if value < -EPS:
        return "Loss"
    return "Draw"


class TreeLens(Lens):
    id = "tree"
    title = "Game tree"
    icon = "tree"
    blurb = "Solve the tree: what is every move worth with best play?"
    concepts = ("game-tree", "minimax", "backward-induction", "branching-factor",
                "symmetry", "heuristic", "solved-game")
    order = 20
    options = (
        {"name": "budget", "label": "Solver budget (positions)", "type": "int",
         "default": 20000, "min": 100, "max": 400000, "step": 1000},
        {"name": "depth", "label": "Search depth (plies)", "type": "int", "default": 4,
         "min": 1, "max": 8, "step": 1},
    )

    #: Skip the exact attempt when random playouts say the tree has more
    #: than 10^this lines (it cannot fit any budget).
    skip_exact_log10 = 15
    #: Give up the exact attempt after this many seconds (slow engines).
    exact_seconds = 1.5
    #: Replies shown per move in the tree preview.
    preview_replies = 6

    def applies(self, game: Game) -> bool:
        return (game.num_players == 2 and game.perfect_information
                and not game.stochastic and not game.simultaneous)

    # ------------------------------------------------------------------ run
    def run(self, session, options):
        g, s = session.game, session.state
        t0 = time.perf_counter()
        if session.terminal or g.is_terminal(s):
            return self._terminal(g, s)
        mover = g.current_player(s)
        actions = g.legal_actions(s)
        budget = self.option(options, "budget")
        depth = self.option(options, "depth")

        est = estimate_size(g, s)
        sizeable = est["log10Size"] <= self.skip_exact_log10
        evaluator = None
        if sizeable:
            evaluator = self._try_exact(g, s, mover, budget)
        mode = "exact"
        if evaluator is None:
            if g.heuristic(s, mover) is not None:
                mode, evaluator = "heuristic", self._heuristic(g, s, mover, depth)
            else:
                return self._too_big(g, s, mover, actions, est, time.perf_counter() - t0)
        return self._result(g, s, mover, actions, mode, evaluator, est, depth, t0)

    # ----------------------------------------------------------- evaluators
    def _try_exact(self, g: Game, s, mover: int, budget: int):
        probe = Probe(g, time.perf_counter() + self.exact_seconds)
        solver = Solver(probe, budget)
        sign = 1.0 if mover == 0 else -1.0
        try:
            solver.value(s)
        except TooBig:
            return None
        probe.deadline = None       # every later lookup is a memo hit

        def value(state, plies_left=None):
            return sign * solver.value(state), True

        value.probe, value.solver = probe, solver
        return value

    def _heuristic(self, g: Game, s, mover: int, depth: int):
        probe = Probe(g)
        sign = 1.0 if mover == 0 else -1.0

        def value(state, plies_left=None):
            left = depth - 1 if plies_left is None else plies_left
            exact = g.is_terminal(state)
            return sign * alphabeta(probe, state, max(left, 0)), exact

        value.probe, value.solver = probe, None
        return value

    # --------------------------------------------------------------- result
    def _result(self, g, s, mover, actions, mode, value: Callable, est, depth, t0):
        exact = mode == "exact"
        rows = []
        for a in actions:
            v, is_exact = value(g.apply_action(s, a))
            rows.append({"a": a, "label": g.action_label(s, a), "value": round(v, 4),
                         "text": self._text(v, exact or is_exact), "exact": exact or is_exact})
        best_value = max(r["value"] for r in rows)
        for r in rows:
            r["best"] = r["value"] >= best_value - 1e-6
        classes = [c for c in g.action_classes(s, actions)]
        by_action = {r["a"]: r for r in rows}
        symmetry = {
            "moves": len(actions), "decisions": len(classes),
            "classes": [{"members": list(c), "labels": [by_action[a]["label"] for a in c],
                         "value": by_action[c[0]]["value"], "text": by_action[c[0]]["text"],
                         "best": by_action[c[0]]["best"]} for c in classes],
        }
        pv = self._principal_variation(g, s, value, exact, depth)
        probe, solver = value.probe, value.solver
        stats = {"searched": probe.nodes, "distinct": len(solver.memo) if solver else None,
                 "branching": round(probe.branching, 2),
                 "depth": len(pv) if exact else depth,
                 "seconds": round(time.perf_counter() - t0, 3)}
        return {
            "mode": mode, "mover": mover, "moverName": g.seat_label(mover),
            "value": best_value, "text": self._text(best_value, exact),
            "outcome": exact_text(best_value).lower() if exact else None,
            "tooBig": False, "actions": rows,
            "best": [r["a"] for r in rows if r["best"]],
            "overlay": self._overlay(rows), "symmetry": symmetry, "stats": stats,
            "pv": [lbl for _, lbl in pv], "tree": self._tree(g, s, classes, rows, value, depth),
            "estimate": est,
        }

    @staticmethod
    def _text(v: float, exact: bool) -> str:
        return exact_text(v) if exact else f"{v:+.2f}"

    @staticmethod
    def _overlay(rows: list[dict]) -> dict:
        lo = min(r["value"] for r in rows)
        out = {}
        for r in rows:
            tone = "best" if r["best"] else ("bad" if r["value"] <= lo + 1e-6 else "neutral")
            out[str(r["a"])] = {"text": r["text"], "tone": tone, "value": r["value"]}
        return {"actions": out}

    def _principal_variation(self, g, s, value, exact: bool, depth: int, cap: int = 30):
        """Best play from ``s``: ``[(action, label)]``. Immediate wins come first."""
        pv = []
        state = s
        limit = cap if exact else depth
        while not g.is_terminal(state) and len(pv) < limit:
            legal = g.legal_actions(state)
            mover = g.current_player(state)
            sign = 1.0 if mover == 0 else -1.0
            scored = []
            for a in legal:
                child = g.apply_action(state, a)
                left = None if exact else depth - len(pv) - 1
                v, _ = value(child, left)
                # ``value`` is from the root mover's side; convert to this mover's.
                root_sign = 1.0 if g.current_player(s) == 0 else -1.0
                scored.append((a, child, v * root_sign * sign))
            top = max(v for _, _, v in scored)
            best = [(a, c) for a, c, v in scored if v >= top - 1e-6]
            pick = next(((a, c) for a, c in best if g.is_terminal(c)), best[0])
            pv.append((pick[0], g.action_label(state, pick[0])))
            state = pick[1]
        return pv

    def _tree(self, g, s, classes, rows, value, depth) -> dict:
        by_action = {r["a"]: r for r in rows}
        children = []
        for members in classes:
            a = members[0]
            row = by_action[a]
            child_state = g.apply_action(s, a)
            node = {"a": a, "label": row["label"], "size": len(members), "value": row["value"],
                    "text": row["text"], "best": row["best"], "children": [], "more": 0}
            if not g.is_terminal(child_state):
                replies = []
                legal = g.legal_actions(child_state)
                for group in g.action_classes(child_state, legal):
                    r = group[0]
                    gs = g.apply_action(child_state, r)
                    v, is_exact = value(gs, depth - 2 if depth > 1 else 0)
                    replies.append({"a": r, "label": g.action_label(child_state, r),
                                    "size": len(group), "value": round(v, 4),
                                    "text": self._text(v, is_exact or row["exact"]),
                                    "best": False})
                replies.sort(key=lambda x: x["value"])
                if replies:
                    low = replies[0]["value"]
                    for x in replies:
                        x["best"] = x["value"] <= low + 1e-6
                node["children"] = replies[:self.preview_replies]
                node["more"] = max(0, len(replies) - self.preview_replies)
            children.append(node)
        root_best = max(r["value"] for r in rows)
        return {"label": "now", "value": root_best, "children": children, "more": 0,
                "text": "" }

    def _terminal(self, g, s) -> dict:
        rets = g.returns(s)
        return {"mode": "terminal", "mover": None, "moverName": "", "value": None,
                "text": "game over", "outcome": None, "tooBig": False, "actions": [],
                "best": [], "overlay": {"actions": {}},
                "symmetry": {"moves": 0, "decisions": 0, "classes": []},
                "stats": {"searched": 0, "distinct": 0, "branching": 0.0, "depth": 0,
                          "seconds": 0.0},
                "pv": [], "tree": None, "estimate": None, "returns": list(rets)}

    def _too_big(self, g, s, mover, actions, est, seconds) -> dict:
        classes = g.action_classes(s, actions)
        return {
            "mode": "estimate", "mover": mover, "moverName": g.seat_label(mover),
            "value": None, "text": "too big", "outcome": None, "tooBig": True,
            "actions": [], "best": [], "overlay": {"actions": {}},
            "symmetry": {"moves": len(actions), "decisions": len(classes),
                         "classes": [{"members": list(c),
                                      "labels": [g.action_label(s, a) for a in c],
                                      "value": None, "text": "", "best": False}
                                     for c in classes]},
            "stats": {"searched": 0, "distinct": None, "branching": est["branching"],
                      "depth": round(est["length"]), "seconds": round(seconds, 3)},
            "pv": [], "tree": None, "estimate": est,
        }
