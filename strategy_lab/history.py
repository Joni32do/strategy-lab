"""Your history: a profile and an append-only event log on disk.

Everything lives in one data directory (default ``./data``, override with
the ``STRATEGY_LAB_DATA`` environment variable):

``profile.json``
    name, tutorial progress and settings (skin, explorer mode, speed).
``history.jsonl``
    one JSON event per line, newest last. Event types:

    * ``game``: a finished game ``{id, game, params, seat, bots, outcome,
      returns, score, steps, timeout, seed, log}``. ``id`` is the
      browser's session id, so a game is never recorded twice.
    * ``lens``: a lens was opened ``{game, lens}``.
    * ``sim``: a card stack was simulated ``{game, bot, stack, n, wins,
      draws, losses}``.
    * ``concept``: a concept card was read in the tutorial ``{concept}``.

Progress (unlocked games, stars, learned concepts) is *derived* from the
events by :mod:`strategy_lab.learn.progress`, never stored, so it can
never drift out of sync.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_PROFILE: dict[str, Any] = {
    "name": "",
    "created": 0,
    "tutorial": {"intro": False, "done": [], "skipped": False},
    "settings": {"skin": "lab", "unlockAll": False, "speed": 1.0, "motion": True},
}


def default_dir() -> Path:
    return Path(os.environ.get("STRATEGY_LAB_DATA", "data")).resolve()


def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Store:
    """Profile + event log in ``data_dir``. Thread-safe for one process."""

    def __init__(self, data_dir: Path | str | None = None):
        self.dir = Path(data_dir) if data_dir else default_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = self.dir / "profile.json"
        self.history_path = self.dir / "history.jsonl"
        self._lock = threading.Lock()
        self._cache: list[dict] | None = None

    # ------------------------------------------------------------- profile
    def profile(self) -> dict:
        with self._lock:
            if self.profile_path.exists():
                try:
                    stored = json.loads(self.profile_path.read_text())
                except json.JSONDecodeError:
                    stored = {}
            else:
                stored = {}
            prof = _merge(DEFAULT_PROFILE, stored)
            if not prof["created"]:
                prof["created"] = int(time.time())
                self.profile_path.write_text(json.dumps(prof, indent=2))
            return prof

    def patch_profile(self, patch: dict) -> dict:
        """Merge ``patch`` into the profile. Only known top-level keys are kept."""
        allowed = {k: v for k, v in patch.items() if k in DEFAULT_PROFILE and k != "created"}
        prof = _merge(self.profile(), allowed)
        with self._lock:
            self.profile_path.write_text(json.dumps(prof, indent=2))
        return prof

    # -------------------------------------------------------------- events
    def events(self, type_: str | None = None, game: str | None = None) -> list[dict]:
        with self._lock:
            if self._cache is None:
                self._cache = []
                if self.history_path.exists():
                    for line in self.history_path.read_text().splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            self._cache.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            evs = self._cache
        return [e for e in evs if (type_ is None or e.get("type") == type_)
                and (game is None or e.get("game") == game)]

    def append(self, event: dict) -> bool:
        """Append an event. Returns False if an event with the same ``id`` exists."""
        event = {"ts": int(time.time()), **event}
        if event.get("id") and any(e.get("id") == event["id"] for e in self.events()):
            return False
        with self._lock:
            with self.history_path.open("a") as f:
                f.write(json.dumps(event, separators=(",", ":")) + "\n")
            if self._cache is not None:
                self._cache.append(event)
        return True

    def reset(self) -> None:
        """Forget everything: profile and history."""
        with self._lock:
            for p in (self.profile_path, self.history_path):
                if p.exists():
                    p.unlink()
            self._cache = None
