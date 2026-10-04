# Strategy Lab

**Play a game. Then find its best strategy.**

Strategy Lab is a set of games built for exploring strategy. You play
against bots with personalities, then look at the same position through
*lenses*: the odds of every roll, the game tree, Nash equilibria, a
learning agent's value function. You write down what you found as rule
cards and test them on 100 games. Every idea you meet lands on your
cheatsheet.

```bash
git submodule update --init catanatron Gymnasium
uv run python -m strategy_lab serve --dev      # http://127.0.0.1:8000
```

## What is inside

- **A learning path in seven chapters**: Chance, Game Trees, Luck Meets
  Skill, Outguess, Hidden Cards, Learning Machines, Many Players. Games open
  one after another; *Explorer mode* opens all of them.
- **A tutorial**: four intro slides, then short coach marks.
- **Your history**: every finished game is kept in `data/history.jsonl`,
  with records per game and replays.
- **Lenses**: Cards, Odds, Game tree, Nash, Learn, Model and Trading.
- **Skins**: Lab (dark), Paper (hand-drawn) and Minimal (characters only).
- **Engines**: native Python games, plus adapters for
  [OpenSpiel](https://github.com/google-deepmind/open_spiel) (chess, skat,
  backgammon, Kuhn poker, our Doppelkopf), Gymnasium (CartPole) and
  catanatron (Catan).

## Built on inheritance

```
Game                       strategy_lab/core/game.py (OpenSpiel-shaped API)
 +- MNKGame                k in a row: Tic-Tac-Toe, Connect Four
 +- DiceGame               Pig, Qwixx
 |   +- RollAndMoveGame    Snakes & Ladders, Mensch aergere dich nicht, ...
 +- MatrixGame             Rock-Paper-Scissors, Prisoner's Dilemma, ...
 +- SinglePlayerGame       bandit, FrozenLake, Cliff Walking
 +- SpielGame / GymGame    external engines
```

Views follow the same idea in the browser: `GridView`, `DiceView`,
`MatrixView` and more draw scene parts, and skins subclass them.

## Add a game and iterate while playing

```bash
uv run python -m strategy_lab new my_game     # a playable draft in the Workbench
uv run python -m strategy_lab serve --dev     # edit, save, keep playing
uv run python -m strategy_lab check my_game   # conformance tests
```

Saving the file restarts the server and replays your open game under the
new rules. See `docs/adding-a-game.md`.

## Documentation and tests

```bash
uv run sphinx-build -b html docs docs/_build/html
uv run pytest -q
```

The `doppelkopf/` package (our OpenSpiel Doppelkopf with its own bots and
web UI) and `rust_cli_implementation/` (a terminal take on the same ideas)
live alongside the app.
