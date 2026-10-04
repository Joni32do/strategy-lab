"""Progress: what is unlocked, which stars are earned, which concepts are learned.

Everything here is computed from the event log (:mod:`strategy_lab.history`).

Unlock rules
------------
* Inside a chapter, games open one after another: a game opens when the
  previous one has been played to the end once.
* The first chapter is open from the start. A later chapter opens when two
  games of the chapter before it are finished (or all, if it has fewer).
* Drafts and the Workbench are always open. Explorer mode
  (``settings.unlockAll``) opens everything.

A concept card is learned when you finish a game that teaches it, or when
the tutorial shows it to you.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from strategy_lab.core.game import Challenge, Game
from strategy_lab.learn.curriculum import CHAPTERS, PATH_CHAPTERS

CHAPTER_GATE = 2


def _games_by_chapter(games: Iterable[type[Game]]) -> dict[str, list[type[Game]]]:
    by: dict[str, list[type[Game]]] = defaultdict(list)
    for g in games:
        by["workbench" if g.draft else g.chapter].append(g)
    for lst in by.values():
        lst.sort(key=lambda g: (g.order, g.name))
    return by


def challenge_met(ch: Challenge, game_id: str, events: list[dict]) -> bool:
    games = [e for e in events if e.get("type") == "game" and e.get("game") == game_id]
    if ch.kind == "finish":
        return bool(games)
    if ch.kind in ("win", "draw"):
        return any(e.get("outcome") == ch.kind and (not ch.bot or ch.bot in e.get("bots", []))
                   for e in games)
    if ch.kind == "score":
        return any((e.get("score") or 0) >= ch.value for e in games)
    if ch.kind == "lens":
        return any(e.get("type") == "lens" and e.get("game") == game_id
                   and e.get("lens") == ch.lens for e in events)
    if ch.kind == "sim":
        for e in events:
            if e.get("type") != "sim" or e.get("game") != game_id:
                continue
            if ch.bot and e.get("bot") != ch.bot:
                continue
            n = e.get("n", 0)
            if ch.metric == "no_loss" and n >= 100 and e.get("losses", 1) == 0:
                return True
            if ch.metric == "winrate" and n and e.get("wins", 0) / n >= ch.value:
                return True
        return False
    return False


def compute(games: list[type[Game]], events: list[dict], settings: dict) -> dict:
    """The full progress picture for the gallery and the profile page."""
    finished = {e["game"] for e in events if e.get("type") == "game"}
    by = _games_by_chapter(games)
    unlock_all = bool(settings.get("unlockAll"))

    chapter_open: dict[str, bool] = {}
    prev_done = None
    for i, cid in enumerate(PATH_CHAPTERS):
        members = by.get(cid, [])
        if i == 0:
            chapter_open[cid] = True
        else:
            prev_members = by.get(PATH_CHAPTERS[i - 1], [])
            need = min(CHAPTER_GATE, len(prev_members))
            chapter_open[cid] = chapter_open[PATH_CHAPTERS[i - 1]] and prev_done >= need
        prev_done = sum(1 for g in members if g.id in finished)
    chapter_open["workbench"] = True

    unlocked: set[str] = set()
    for cid, members in by.items():
        if unlock_all or cid == "workbench":
            unlocked.update(g.id for g in members)
            continue
        if not chapter_open.get(cid, False):
            continue
        for j, g in enumerate(members):
            if j == 0 or members[j - 1].id in finished or g.id in finished:
                unlocked.add(g.id)

    stars: dict[str, list[str]] = {}
    for g in games:
        got = [c.id for c in g.challenges if challenge_met(c, g.id, events)]
        if got:
            stars[g.id] = got

    concepts = set()
    for g in games:
        if g.id in finished:
            concepts.update(g.concepts)
    concepts.update(e["concept"] for e in events if e.get("type") == "concept")

    return {
        "finished": sorted(finished),
        "unlocked": sorted(unlocked),
        "chapters": {cid: (unlock_all or chapter_open.get(cid, False))
                     for cid in [c.id for c in CHAPTERS]},
        "stars": stars,
        "concepts": sorted(concepts),
    }


def diff(before: dict, after: dict) -> dict:
    """What a new event just achieved (for the celebration toast)."""
    new_stars = {g: [s for s in ids if s not in before["stars"].get(g, [])]
                 for g, ids in after["stars"].items()}
    return {
        "games": [g for g in after["unlocked"] if g not in before["unlocked"]],
        "chapters": [c for c, ok in after["chapters"].items()
                     if ok and not before["chapters"].get(c)],
        "stars": {g: s for g, s in new_stars.items() if s},
        "concepts": [c for c in after["concepts"] if c not in before["concepts"]],
    }


def stats(events: list[dict]) -> dict:
    """Per-game and overall numbers for the history page."""
    per: dict[str, dict] = defaultdict(lambda: {"played": 0, "win": 0, "draw": 0, "loss": 0,
                                                "best": None, "last": 0})
    for e in events:
        if e.get("type") != "game":
            continue
        row = per[e["game"]]
        row["played"] += 1
        row[e.get("outcome", "draw")] = row.get(e.get("outcome", "draw"), 0) + 1
        score = e.get("score")
        if score is not None and (row["best"] is None or score > row["best"]):
            row["best"] = score
        row["last"] = max(row["last"], e.get("ts", 0))
    days = sorted({e.get("ts", 0) // 86400 for e in events if e.get("type") == "game"})
    streak = 0
    if days:
        streak = 1
        for a, b in zip(reversed(days[:-1]), reversed(days[1:])):
            if b - a == 1:
                streak += 1
            else:
                break
    games = [e for e in events if e.get("type") == "game"]
    return {
        "games": dict(per),
        "total": len(games),
        "wins": sum(1 for e in games if e.get("outcome") == "win"),
        "sims": sum(1 for e in events if e.get("type") == "sim"),
        "lenses": sum(1 for e in events if e.get("type") == "lens"),
        "dayStreak": streak,
    }
