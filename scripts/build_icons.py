"""Build web/assets/icons.json from the Lucide icon set.

Icons are referenced by short names (``Game.icon = "dice"``). This script
maps those names to Lucide icons (https://lucide.dev, ISC license) and
stores each icon's inner SVG markup. To add an icon: add a line to
``ICONS``, then run::

    npm pack lucide-static && mkdir lucide && tar xzf lucide-static-*.tgz -C lucide
    uv run python scripts/build_icons.py lucide/package/icons

Values starting with ``<`` are inline SVG drawn here (for shapes Lucide lacks).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ICONS = {
    # interface
    "play": "play", "pause": "pause", "step": "step-forward", "undo": "undo-2",
    "reset": "rotate-ccw", "menu": "menu", "close": "x", "check": "check",
    "lock": "lock", "unlock": "lock-open", "info": "info", "book": "book-open",
    "cheatsheet": "library", "history": "history", "settings": "settings",
    "palette": "palette", "arrow-right": "arrow-right", "arrow-left": "arrow-left",
    "chevron-right": "chevron-right", "chevron-down": "chevron-down", "search": "search",
    "graduation": "graduation-cap", "fast": "fast-forward", "skip": "skip-forward",
    "sun": "sun", "moon": "moon", "sliders": "sliders-horizontal", "help": "circle-help",
    "pen": "pen-line", "notebook": "notebook-pen", "medal": "medal", "party": "party-popper",
    "rocket": "rocket", "flame": "flame", "badge": "badge-check", "gamepad": "gamepad-2",
    "copy": "copy",
    # games and concepts
    "dice": "dice-5", "dices": "dices", "coin": "coins", "pig": "piggy-bank",
    "snake": "worm", "grid3": "grid-3x3", "discs": "circle-dot", "sticks": "tally-5",
    "chess": "chess-knight", "king": "chess-king", "castle": "castle",
    "race": "flag-triangle-right", "pawn": "chess-pawn", "house": "house", "home": "house",
    "money": "banknote", "road": "route", "sheet": "sheet", "hand": "hand",
    "hands": "hand-metal", "scissors": "scissors", "handshake": "handshake",
    "deer": "trees", "rabbit": "rabbit", "cards": "gallery-horizontal-end",
    "spade": "spade", "heart": "heart", "club": "club", "diamond": "diamond",
    "crown": "crown", "slot": "cherry", "gem": "gem", "cherry": "cherry",
    "snowflake": "snowflake", "mountain": "mountain", "cart": "move-horizontal",
    "hexagon": "hexagon", "wheat": "wheat", "anchor": "anchor", "sword": "sword",
    "fork": "split", "barrier": "construction", "mirror": "flip-horizontal-2",
    "corner": "square-dashed-top-solid", "edge": "minus", "trophy": "trophy",
    "shield": "shield", "target": "target", "flag": "flag", "star": "star",
    "sparkle": "sparkles", "bolt": "zap", "brain": "brain", "tree": "network",
    "chart": "chart-line", "eye": "eye", "bot": "bot", "robot": "bot-message-square",
    "smile": "smile", "user": "user", "people": "users", "scale": "scale",
    "percent": "percent", "sigma": "sigma", "shuffle": "shuffle", "compass": "compass",
    "map": "map", "lightbulb": "lightbulb", "hourglass": "hourglass", "timer": "timer",
    "footprints": "footprints", "puzzle": "puzzle", "wrench": "wrench", "race-car": "rocket",
    "people-arrows": "users", "layers": "layers", "fist": "hand-fist",
    "ladder": ('<path d="M7 3v18" /><path d="M17 3v18" /><path d="M7 7h10" />'
               '<path d="M7 12h10" /><path d="M7 17h10" />'),
}


def inner_svg(text: str) -> str:
    body = re.search(r"<svg[^>]*>(.*)</svg>", text, re.S).group(1)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    return " ".join(line.strip() for line in body.strip().splitlines())


def main(src: str) -> None:
    folder = Path(src)
    out = {}
    for name, ref in ICONS.items():
        if ref.startswith("<"):
            out[name] = ref
            continue
        path = folder / f"{ref}.svg"
        if not path.exists():
            raise SystemExit(f"missing Lucide icon {ref!r} for {name!r}")
        out[name] = inner_svg(path.read_text())
    dest = Path(__file__).resolve().parents[1] / "web" / "assets" / "icons.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=0, sort_keys=True))
    print(f"wrote {len(out)} icons to {dest}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "lucide/package/icons")
