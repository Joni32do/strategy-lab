"""Find every game: import all modules under :mod:`strategy_lab.games`.

A game registers itself by existing: any subclass of
:class:`~strategy_lab.core.game.Game` that defines its own ``id`` is
concrete. No list to edit, no decorator to remember.

A module that fails to import (a typo while you iterate, a missing
optional engine such as catanatron) does not take the server down; it is
reported in :func:`broken` and shown in the Workbench instead.
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback

from strategy_lab.core.game import Game

_games: dict[str, type[Game]] = {}
_broken: dict[str, str] = {}
_loaded = False


def _subclasses(cls: type) -> list[type]:
    out = []
    for sub in cls.__subclasses__():
        out.append(sub)
        out.extend(_subclasses(sub))
    return out


def discover(force: bool = False) -> dict[str, type[Game]]:
    """Import all game modules once and index the concrete games by id."""
    global _loaded
    if _loaded and not force:
        return _games
    import strategy_lab.games as pkg
    _broken.clear()
    for info in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 - report, never crash the server
            _broken[info.name] = traceback.format_exc(limit=6)
    _games.clear()
    for cls in _subclasses(Game):
        if not cls.is_concrete():
            continue
        if cls.id in _games and _games[cls.id] is not cls:
            other = _games[cls.id]
            raise ValueError(f"duplicate game id {cls.id!r}: {other.__module__}."
                             f"{other.__name__} and {cls.__module__}.{cls.__name__}")
        _games[cls.id] = cls
    _loaded = True
    return _games


def games() -> list[type[Game]]:
    """All concrete game classes, in learning-path order."""
    from strategy_lab.learn.curriculum import CHAPTERS
    rank = {c.id: i for i, c in enumerate(CHAPTERS)}
    return sorted(discover().values(),
                  key=lambda c: (c.draft, rank.get(c.chapter, len(rank)), c.order, c.name))


def get(game_id: str) -> type[Game]:
    try:
        return discover()[game_id]
    except KeyError:
        raise KeyError(f"unknown game {game_id!r}") from None


def create(game_id: str, params: dict | None = None) -> Game:
    """Instantiate a game with variant parameters."""
    return get(game_id)(**(params or {}))


def broken() -> dict[str, str]:
    """Modules that failed to import, with a short traceback each."""
    discover()
    return dict(_broken)
