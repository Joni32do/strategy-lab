"""Scenes: the JSON vocabulary between games (Python) and views (browser).

A game never draws anything. Its :meth:`~strategy_lab.core.game.Game.scene`
returns a *scene*: a list of *parts*, each a plain dict whose ``"view"``
key names the frontend view class that renders it (``web/js/views/``).
New games combine the stock parts below and need no JavaScript at all.

Interaction: any element that carries an ``action`` becomes clickable and
sends that action. Lenses annotate the same elements by action (win rates,
minimax values, Q-values), so a board shows analysis without knowing about
it.

Shared vocabulary
-----------------
``owner``
    a seat index; views color it with the player palette ``--p0..--p5``.
``tone``
    a styling hint. Common values: ``light`` ``dark`` (checkerboards),
    ``start`` ``goal`` ``hole`` ``wall`` ``cliff`` ``ice`` ``safe``
    ``ladder`` ``snake`` ``hot`` ``cold`` ``muted`` ``good`` ``bad``,
    ``p0``..``p5`` (player colored), dice colors ``white`` ``red``
    ``yellow`` ``green`` ``blue``, ``last`` (the most recent move),
    and Monopoly groups ``brown``
    ``lightblue`` ``pink`` ``orange`` ``red`` ``yellow`` ``green`` ``navy``.
``icon``
    a name from the frontend icon set (``web/js/icons.js``).

Every helper only builds dicts and drops empty optional fields, so the
JSON stays small. Unknown keys are allowed: custom views may read more.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from strategy_lab.core.game import Action


def _clean(d: dict) -> dict:
    """Drop keys whose value is None, empty string or empty list/tuple."""
    return {k: v for k, v in d.items() if v is not None and v != "" and v != [] and v != ()}


# --------------------------------------------------------------------------- #
# The scene
# --------------------------------------------------------------------------- #
def scene(parts: Sequence[dict], *, players: Sequence[dict] | None = None,
          layout: str = "stack", status: str = "") -> dict:
    """Assemble a scene.

    Args:
        parts: part dicts, rendered in order.
        players: optional scoreboard rows (see :func:`player`). Without it the
            page shows seat names and current returns.
        layout: ``"stack"`` (parts top to bottom) or ``"split"`` (first part
            large, the rest in a side column).
        status: headline above the board, e.g. ``"Roll or hold?"``.
    """
    return _clean({"parts": list(parts), "players": list(players) if players else None,
                   "layout": layout, "status": status})


def player(name: str, *, score: Any = None, sub: str = "", active: bool = False,
           owner: int | None = None) -> dict:
    """One scoreboard row. ``sub`` is a second line ("3 tokens home")."""
    return _clean({"name": name, "score": score, "sub": sub, "active": active or None,
                   "owner": owner})


# --------------------------------------------------------------------------- #
# grid: boards of cells (Tic-Tac-Toe, Connect Four, chess, grid worlds)
# --------------------------------------------------------------------------- #
def piece(owner: int | None = None, shape: str = "token", glyph: str = "",
          label: str = "") -> dict:
    """A piece on a cell.

    ``shape``: ``x`` ``o`` ``disc`` ``token`` ``glyph`` (draws ``glyph``,
    e.g. a chess letter ``"K"``; uppercase means white) or ``agent``.
    """
    return _clean({"owner": owner, "shape": shape, "glyph": glyph, "label": label})


def cell(text: str = "", *, pieces: Iterable[dict] = (), tone: str = "",
         action: Action | None = None, label: str = "", badge: str = "",
         icon: str = "", arrow: str = "") -> dict:
    """One grid cell.

    Args:
        text: large center text (a number, a letter).
        pieces: pieces standing on the cell.
        tone: background hint (see module docs).
        action: clicking the cell plays this action.
        label: small corner label (square numbers in Snakes & Ladders).
        badge: small pill (e.g. a reward ``"+1"``).
        icon: icon name drawn in the cell.
        arrow: ``up`` ``down`` ``left`` ``right``: a policy arrow.
    """
    return _clean({"text": text, "pieces": list(pieces), "tone": tone, "action": action,
                   "label": label, "badge": badge, "icon": icon, "arrow": arrow})


def grid(rows: int, cols: int, cells: Sequence[dict | None], *, style: str = "board",
         links: Iterable[dict] = (), lines: Iterable[Sequence[int]] = (),
         coords: bool = False, caption: str = "") -> dict:
    """A ``rows x cols`` board, cells in row-major order (``None`` = no cell).

    Args:
        style: ``board`` (lines between cells), ``checker`` (alternating
            light/dark), ``tiles`` (separate rounded tiles) or ``holes``
            (a Connect Four style frame).
        links: arrows between cells, ``{"from": i, "to": j, "kind": k}`` with
            ``kind`` in ``up`` (ladder), ``down`` (snake) or ``arrow``.
        lines: index sequences to highlight (a winning line).
        coords: draw file/rank labels (a..h, 1..8) around the board.
    """
    if len(cells) != rows * cols:
        raise ValueError(f"grid needs {rows * cols} cells, got {len(cells)}")
    return _clean({"view": "grid", "rows": rows, "cols": cols, "cells": list(cells),
                   "style": style, "links": list(links), "lines": [list(l) for l in lines],
                   "coords": coords or None, "caption": caption})


def link(src: int, dst: int, kind: str = "arrow") -> dict:
    return {"from": src, "to": dst, "kind": kind}


# --------------------------------------------------------------------------- #
# track: spaces along a path (Monopoly ring, Game of Life road)
# --------------------------------------------------------------------------- #
def space(label: str, *, sub: str = "", tone: str = "", icon: str = "",
          owner: int | None = None, level: int = 0, action: Action | None = None) -> dict:
    """One space of a track. ``level``: houses, upgrades, a small number."""
    return _clean({"label": label, "sub": sub, "tone": tone, "icon": icon,
                   "owner": owner, "level": level or None, "action": action})


def token(owner: int, at: int, label: str = "") -> dict:
    return _clean({"owner": owner, "at": at, "label": label})


def track(spaces: Sequence[dict], tokens: Iterable[dict] = (), *, shape: str = "ring",
          caption: str = "") -> dict:
    """A path of spaces with tokens on it.

    ``shape``: ``ring`` (around a square, like Monopoly), ``line`` or
    ``serpentine`` (rows that wind back and forth).
    """
    return _clean({"view": "track", "spaces": list(spaces), "tokens": list(tokens),
                   "shape": shape, "caption": caption})


# --------------------------------------------------------------------------- #
# dice
# --------------------------------------------------------------------------- #
def die(value: int, *, sides: int = 6, tone: str = "white", held: bool = False,
        action: Action | None = None, label: str = "") -> dict:
    return _clean({"value": value, "sides": sides if sides != 6 else None, "tone": tone,
                   "held": held or None, "action": action, "label": label})


def dice(dice_: Iterable[dict], *, caption: str = "", fresh: bool = False) -> dict:
    """A row of dice. ``fresh=True`` plays the roll animation."""
    return _clean({"view": "dice", "dice": list(dice_), "caption": caption,
                   "fresh": fresh or None})


# --------------------------------------------------------------------------- #
# heaps: piles of identical items (Nim)
# --------------------------------------------------------------------------- #
def heap(count: int, label: str = "", actions: Sequence[Action | None] = ()) -> dict:
    """``actions[i]`` takes ``i + 1`` items (``None`` where not allowed)."""
    return _clean({"count": count, "label": label, "actions": list(actions)})


def heaps(heaps_: Sequence[dict], *, caption: str = "") -> dict:
    return _clean({"view": "heaps", "heaps": list(heaps_), "caption": caption})


# --------------------------------------------------------------------------- #
# matrix: a payoff table (simultaneous-move games)
# --------------------------------------------------------------------------- #
def matrix(row_labels: Sequence[str], col_labels: Sequence[str],
           payoffs: Sequence[Sequence[Sequence[float]]], *, row_player: int = 0,
           col_player: int = 1, row_actions: Sequence[Action | None] = (),
           highlight: tuple[int, int] | None = None,
           history: Iterable[tuple[int, int]] = (), caption: str = "") -> dict:
    """A bimatrix: ``payoffs[i][j] = [row player's payoff, column player's]``.

    ``row_actions`` make rows clickable; ``highlight`` marks the last joint
    choice; ``history`` lists earlier ``(row, col)`` pairs.
    """
    return _clean({"view": "matrix", "rowLabels": list(row_labels),
                   "colLabels": list(col_labels),
                   "payoffs": [[list(c) for c in r] for r in payoffs],
                   "rowPlayer": row_player, "colPlayer": col_player,
                   "rowActions": list(row_actions),
                   "highlight": list(highlight) if highlight else None,
                   "history": [list(h) for h in history], "caption": caption})


# --------------------------------------------------------------------------- #
# arms: choices with running statistics (multi-armed bandits)
# --------------------------------------------------------------------------- #
def arm(label: str, *, pulls: int = 0, mean: float | None = None, action: Action | None = None,
        tone: str = "", sub: str = "") -> dict:
    return _clean({"label": label, "pulls": pulls, "mean": mean, "action": action,
                   "tone": tone, "sub": sub})


def arms(arms_: Sequence[dict], *, caption: str = "") -> dict:
    return _clean({"view": "arms", "arms": list(arms_), "caption": caption})


# --------------------------------------------------------------------------- #
# sheet: a roll-and-write score sheet (Qwixx)
# --------------------------------------------------------------------------- #
def sheet_cell(label: str, *, crossed: bool = False, action: Action | None = None,
               lock: bool = False, tone: str = "") -> dict:
    """One box; ``tone="muted"`` greys out skipped or closed numbers."""
    return _clean({"label": label, "crossed": crossed or None, "action": action,
                   "lock": lock or None, "tone": tone})


def sheet_row(color: str, cells: Sequence[dict], *, locked: bool = False,
              score: int | None = None) -> dict:
    return _clean({"color": color, "cells": list(cells), "locked": locked or None,
                   "score": score})


def sheet(title: str, rows: Sequence[dict], *, owner: int | None = None,
          penalties: int = 0, max_penalties: int = 4, penalty_action: Action | None = None,
          score: int | None = None, active: bool = False, compact: bool = False) -> dict:
    """A score sheet. ``compact`` renders a small read-only version (opponents)."""
    return _clean({"view": "sheet", "title": title, "rows": list(rows), "owner": owner,
                   "penalties": penalties, "maxPenalties": max_penalties,
                   "penaltyAction": penalty_action, "score": score,
                   "active": active or None, "compact": compact or None})


# --------------------------------------------------------------------------- #
# cards: a card table (trick-taking games, poker)
# --------------------------------------------------------------------------- #
def playing_card(rank: str, suit: str, *, action: Action | None = None, trump: bool = False,
                 points: int | None = None, faceup: bool = True) -> dict:
    """``suit``: ``C`` ``S`` ``H`` ``D`` (clubs, spades, hearts, diamonds)."""
    return _clean({"rank": rank, "suit": suit, "action": action, "trump": trump or None,
                   "points": points, "faceup": None if faceup else False})


def table(*, seat: int, names: Sequence[str], hand: Sequence[dict],
          hand_sizes: Sequence[int], trick: Sequence[dict] = (), leader: int | None = None,
          to_act: int | None = None, last_trick: dict | None = None,
          taken: Sequence[int] | None = None, badges: Sequence[Sequence[str]] = (),
          center: Sequence[dict] = (), caption: str = "") -> dict:
    """A card table seen from ``seat``.

    ``trick`` holds ``{"seat": s, "card": playing_card(...)}`` entries;
    ``center`` shows extra open cards (a skat, a board card); ``badges[s]``
    lists short tags per seat ("Re", "declarer").
    """
    return _clean({"view": "cards", "seat": seat, "names": list(names), "hand": list(hand),
                   "handSizes": list(hand_sizes), "trick": list(trick), "leader": leader,
                   "toAct": to_act, "lastTrick": last_trick,
                   "taken": list(taken) if taken is not None else None,
                   "badges": [list(b) for b in badges], "center": list(center),
                   "caption": caption})


# --------------------------------------------------------------------------- #
# generic panels
# --------------------------------------------------------------------------- #
def bar(label: str, value: float, *, max: float | None = None, min: float = 0.0,
        tone: str = "", text: str = "") -> dict:
    return _clean({"label": label, "value": value, "max": max, "min": min or None,
                   "tone": tone, "text": text})


def bars(items: Sequence[dict], *, caption: str = "") -> dict:
    """Labeled horizontal bars (scores, money, an observation vector)."""
    return _clean({"view": "bars", "items": list(items), "caption": caption})


def kv(items: Sequence[tuple[str, Any]], *, caption: str = "", owner: int | None = None) -> dict:
    """A small key/value table (a player's finances)."""
    return _clean({"view": "kv", "items": [[k, v] for k, v in items], "caption": caption,
                   "owner": owner})


def buttons(choices: Sequence[tuple[Action, str]], *, caption: str = "",
            sub: Sequence[str] = ()) -> dict:
    """Big choice buttons for actions without a board ("Roll" / "Hold")."""
    out = []
    for i, (a, label) in enumerate(choices):
        out.append(_clean({"action": a, "label": label, "sub": sub[i] if i < len(sub) else ""}))
    return _clean({"view": "buttons", "choices": out, "caption": caption})


def text(body: str, *, mono: bool = False, caption: str = "") -> dict:
    """Plain or monospaced text (the fallback view)."""
    return _clean({"view": "text", "text": body, "mono": mono or None, "caption": caption})


def custom(view: str, **data: Any) -> dict:
    """A part for a game-specific view class registered under ``view``."""
    return {"view": view, **data}
