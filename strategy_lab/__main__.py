"""Command line: ``uv run python -m strategy_lab <command>``.

``serve [--port 8000] [--dev]``
    Run the app. ``--dev`` restarts the server whenever a Python file
    changes and makes the open page reload itself when web files change;
    your current game survives both (it is replayed from its action log).

``new <id> [--name "My Game"]``
    Create ``strategy_lab/games/<id>.py`` from a small working template
    (a draft, shown in the Workbench) and print what to do next.

``check [<id> ...]``
    Run the conformance tests (all games, or only the named ones).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent

TEMPLATE = '''"""{name}: a new game (draft).

Start here: this template is a complete, playable game ("race to {target}":
players take turns adding 1, 2 or 3 to a shared counter; whoever reaches
{target} wins). Replace the rules with yours one method at a time and keep
the dev server running (``uv run python -m strategy_lab serve --dev``):
every save replays your current game under the new rules.

Checklist when the game works:

* pick a better ``icon``, ``chapter`` and ``order``, remove ``draft = True``
* list the ``concepts`` it teaches (ids from strategy_lab/learn/concepts.py)
* add rule cards (@pick / @avoid) and bots that use them
* run ``uv run python -m strategy_lab check {id}``
"""

from __future__ import annotations

from dataclasses import dataclass

from strategy_lab.core import Bot, Challenge, Game, Rulebook, pick, scene


@dataclass
class State:
    total: int = 0
    to_move: int = 0
    last: int = 0


class {cls}(Game):
    id = "{id}"
    name = "{name}"
    icon = "puzzle"
    tagline = "Add 1, 2 or 3. Whoever says {target} wins."
    chapter = "workbench"
    draft = True
    concepts = ("backward-induction",)

    rulebook = Rulebook(
        summary="Two players count up together from 0.",
        steps=(
            ("Your turn", "Add 1, 2 or 3 to the counter."),
            ("Winning", "Whoever brings the counter to exactly {target} wins."),
        ),
    )
    bots = (
        Bot("randy", "Randy Rookie", "Adds a random amount.", 1, icon="dice"),
        Bot("fours", "Four-step Fiona", "Always leaves a multiple of 4.", 3,
            cards=("multiple-of-4",), icon="robot"),
    )
    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-fiona", "Beat Four-step Fiona", "win", 2, bot="fours"),
    )

    TARGET = {target}

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> State:
        return State()

    def current_player(self, s: State) -> int:
        return s.to_move

    def legal_actions(self, s: State) -> list[int]:
        return [n for n in (1, 2, 3) if s.total + n <= self.TARGET]

    def move(self, s: State, a: int) -> None:
        s.total += a
        s.last = a
        s.to_move = 1 - s.to_move

    def is_terminal(self, s: State) -> bool:
        return s.total >= self.TARGET

    def winner(self, s: State) -> int | None:
        return 1 - s.to_move if self.is_terminal(s) else None

    # ----------------------------------------------------------- presentation
    def action_label(self, s: State, a: int) -> str:
        return f"+{{a}}"

    def describe(self, s: State, a: int, player: int) -> str:
        return f"adds {{a}} and says {{s.total + a}}"

    def scene(self, s: State, viewer):
        bar = scene.bars([scene.bar("Counter", s.total, max=self.TARGET,
                                    text=f"{{s.total}} / {{self.TARGET}}")])
        moves = scene.buttons([(a, f"+{{a}}") for a in self.legal_actions(s)]
                              if not self.is_terminal(s) else [])
        return scene.scene([bar, moves], status=f"The counter is at {{s.total}}.")

    # -------------------------------------------------------------- rule cards
    @pick("multiple-of-4", "Leave a multiple of 4",
          "Bring the counter to a number that leaves the opponent a multiple of 4.", "target")
    def card_multiple_of_4(self, s, candidates, player, rng):
        for a in candidates:
            if (self.TARGET - (s.total + a)) % 4 == 0:
                return a
        return None
'''


def cmd_new(args) -> int:
    gid = args.id.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", gid):
        print("id must be lowercase letters, digits and underscores, starting with a letter")
        return 2
    path = PACKAGE / "games" / f"{gid}.py"
    if path.exists():
        print(f"{path} already exists")
        return 1
    name = args.name or gid.replace("_", " ").title()
    cls = "".join(part.capitalize() for part in gid.split("_")) or "NewGame"
    path.write_text(TEMPLATE.format(id=gid, name=name, cls=cls, target=21))
    (PACKAGE / "games" / "__init__.py").touch()
    print(f"created {path.relative_to(PACKAGE.parent)}")
    print("next: uv run python -m strategy_lab serve --dev   (find it in the Workbench)")
    print(f"      uv run python -m strategy_lab check {gid}")
    return 0


def cmd_check(args) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "tests/test_conformance.py"]
    if args.ids:
        cmd += ["-k", " or ".join(args.ids)]
    return subprocess.call(cmd, cwd=PACKAGE.parent)


def cmd_serve(args) -> int:
    from strategy_lab.web import create_app
    app = create_app(args.data, dev=args.dev)
    print(f"Strategy Lab on http://127.0.0.1:{args.port}" + ("  (dev mode)" if args.dev else ""))
    app.run(host=args.host, port=args.port, debug=args.dev, use_reloader=args.dev)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m strategy_lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the app")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--dev", action="store_true", help="auto-reload on file changes")
    s.add_argument("--data", default=None, help="data directory (default ./data)")
    s.set_defaults(fn=cmd_serve)
    n = sub.add_parser("new", help="scaffold a new game")
    n.add_argument("id")
    n.add_argument("--name", default="")
    n.set_defaults(fn=cmd_new)
    c = sub.add_parser("check", help="run conformance tests")
    c.add_argument("ids", nargs="*")
    c.set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
