"""Lenses: ways of looking at a position to find the strategy.

A lens is an analysis tool shown next to the board: the game tree, the
odds, a payoff matrix, a learning curve. Each lens decides which games it
applies to (:meth:`Lens.applies`) and turns the current session into a
JSON result (:meth:`Lens.run`). The frontend has one view class per lens
(``web/js/lenses/``) with the same ``id``.

Board overlay convention
------------------------
A result may contain ``"overlay": {"actions": {...}}`` mapping
``str(action)`` to ``{"text": "+1", "tone": "best"|"good"|"bad"|"neutral",
"value": float}``. The board view puts that badge on whatever element
plays the action (a cell, a die, a button), so every lens can annotate
every board without knowing what it looks like.

Lenses must be quick (well under a second for the default options) and
pure: they never change the session.
"""

from __future__ import annotations

from typing import Any, ClassVar

from strategy_lab.core.game import Game
from strategy_lab.core.session import Session


class Lens:
    """Base class. Subclass, set the metadata, implement two methods."""

    id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    icon: ClassVar[str] = "eye"
    #: One line under the tab title.
    blurb: ClassVar[str] = ""
    #: Concept ids this lens illustrates (linked from the panel).
    concepts: ClassVar[tuple[str, ...]] = ()
    #: Tab order; lower comes first.
    order: ClassVar[int] = 100
    #: Option schema for the panel: a list of dicts with keys ``name``,
    #: ``label``, ``type`` (int, float, bool or choice), ``default``, ``min``,
    #: ``max``, ``step`` and ``choices``.
    options: ClassVar[tuple[dict, ...]] = ()

    def applies(self, game: Game) -> bool:
        """Is this lens useful for ``game``? Called once per game page."""
        raise NotImplementedError

    def run(self, session: Session, options: dict[str, Any]) -> dict:
        """Analyze ``session.state``. Return a JSON-serializable dict."""
        raise NotImplementedError

    # ---------------------------------------------------------------- helpers
    def option(self, options: dict, name: str) -> Any:
        """Read an option, coerced to the schema type, falling back to the default."""
        spec = next((o for o in self.options if o["name"] == name), None)
        if spec is None:
            raise KeyError(name)
        raw = options.get(name, spec.get("default"))
        kind = spec.get("type", "float")
        try:
            if kind == "int":
                v = int(raw)
            elif kind == "float":
                v = float(raw)
            elif kind == "bool":
                v = raw if isinstance(raw, bool) else str(raw).lower() in ("1", "true", "on")
            else:
                v = raw if raw in spec.get("choices", [raw]) else spec.get("default")
        except (TypeError, ValueError):
            v = spec.get("default")
        if kind in ("int", "float"):
            if spec.get("min") is not None:
                v = max(spec["min"], v)
            if spec.get("max") is not None:
                v = min(spec["max"], v)
        return v

    def options_for(self, game: Game) -> tuple[dict, ...]:
        """The option schema shown for ``game``. Override to tailor choices per game."""
        return self.options

    def meta(self, game: Game | None = None) -> dict:
        opts = self.options_for(game) if game is not None else self.options
        return {"id": self.id, "title": self.title, "icon": self.icon, "blurb": self.blurb,
                "concepts": list(self.concepts), "order": self.order,
                "options": [dict(o) for o in opts]}


def overlay(values: dict, best_high: bool = True, fmt: str = "{:+.2f}") -> dict:
    """Build an overlay from ``{action: number}``; the best get tone ``best``."""
    if not values:
        return {"actions": {}}
    best = max(values.values()) if best_high else min(values.values())
    worst = min(values.values()) if best_high else max(values.values())
    out = {}
    for a, v in values.items():
        if abs(v - best) < 1e-9:
            tone = "best"
        elif abs(v - worst) < 1e-9 and best != worst:
            tone = "bad"
        else:
            tone = "neutral"
        out[str(a)] = {"text": fmt.format(v), "tone": tone, "value": v}
    return {"actions": out}
