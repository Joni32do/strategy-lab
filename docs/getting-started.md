# Getting started

Everything runs through [uv](https://docs.astral.sh/uv/). The first command
creates `.venv` and installs the dependencies, including the vendored
`catanatron/` and `Gymnasium/` submodules:

```bash
git submodule update --init catanatron Gymnasium
uv run python -m strategy_lab serve --dev     # http://127.0.0.1:8000
```

`--dev` restarts the server when a Python file changes and reloads the page
when a file in `web/` changes. A running game survives both: it is replayed
from its action log.

## Commands

| Command | What it does |
| --- | --- |
| `uv run python -m strategy_lab serve [--dev] [--port N]` | run the app |
| `uv run python -m strategy_lab new <id>` | scaffold a new game in the Workbench |
| `uv run python -m strategy_lab check [<id> ...]` | conformance tests for all or some games |
| `uv run pytest -q` | the full test suite |
| `uv run sphinx-build -b html docs docs/_build/html` | build this documentation |

## Your data

Profile, tutorial progress and history live in `data/` (`profile.json`,
`history.jsonl`). Set `STRATEGY_LAB_DATA=/some/dir` to keep them elsewhere.
"Reset progress" in the settings menu deletes both files.

## First visit

The app opens with four intro slides, then sends you to the first game
(Pig). Short coach marks explain the board, the lenses, the goals and the
gallery once each. "Replay the tutorial" in the settings starts over.
*Explorer mode* in the same menu opens every game at once.
