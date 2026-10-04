"""Lenses: analysis panels next to the board. See :mod:`strategy_lab.lenses.base`.

Every module in this package is imported by :func:`all_lenses`; each
concrete :class:`~strategy_lab.lenses.base.Lens` subclass with an ``id``
is instantiated once.
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback

from strategy_lab.lenses.base import Lens

_lenses: dict[str, Lens] = {}
_broken: dict[str, str] = {}


def _subclasses(cls):
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


def all_lenses() -> dict[str, Lens]:
    if not _lenses:
        for info in pkgutil.iter_modules(__path__, __name__ + "."):
            if info.name.endswith(".base"):
                continue
            try:
                importlib.import_module(info.name)
            except Exception:  # noqa: BLE001 - report, never crash
                _broken[info.name] = traceback.format_exc(limit=6)
        for cls in _subclasses(Lens):
            if vars(cls).get("id"):
                _lenses[cls.id] = cls()
    return _lenses


def lenses_for(game) -> list[Lens]:
    out = []
    for lens in all_lenses().values():
        try:
            if lens.applies(game):
                out.append(lens)
        except Exception:  # noqa: BLE001 - a lens bug must not hide the game
            continue
    return sorted(out, key=lambda l: (l.order, l.id))


def broken() -> dict[str, str]:
    all_lenses()
    return dict(_broken)
