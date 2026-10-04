# Architecture

```
strategy_lab/
  core/        Game base class, scenes, policies, sessions, search, matches, registry
  families/    base classes shared by a family of games (inheritance)
  games/       one module per concrete game, auto-discovered
  lenses/      analysis panels: odds, cards, tree, nash, rl, model, ...
  learn/       chapters, concept cards, progress (unlocks, stars)
  history.py   profile + event log in data/
  web/app.py   Flask JSON API + static frontend
web/
  js/views/    one View class per scene part type (+ custom/)
  js/lenses/   one LensView class per lens id
  js/skins/    Skin classes that swap in their own View subclasses
  js/ui/       gallery, game page, tutorial, cheatsheet, history
docs/          this documentation (Sphinx + MyST)
tests/         pytest: conformance for every game, API, per-game rules
```

## Three hierarchies

**Games** inherit rules. {class}`~strategy_lab.core.game.Game` defines the
contract in the shape of OpenSpiel's API. A family base class implements a
whole kind of game once; a concrete game mostly sets numbers:

```
Game
 +- MNKGame                 k in a row: rules, symmetry, heuristic, shared cards
 |   +- TicTacToe           3x3, k=3, fork cards
 |   +- ConnectFour         6x7, k=4, gravity
 +- DiceGame                dice chance nodes, dice scenes
 |   +- Pig, Qwixx
 |   +- RollAndMoveGame     tokens on a track
 |       +- SnakesAndLadders, Maedn, ...
 +- MatrixGame              simultaneous normal-form games
 |   +- RockPaperScissors, PrisonersDilemma, ...
 +- SinglePlayerGame        MDPs for reinforcement learning
 |   +- GridWorld -> FrozenLake, CliffWalking
 |   +- Bandit
 +- SpielGame / GymGame     adapters for OpenSpiel and Gymnasium
```

Rule cards are inherited too: "Finish it" and "Block the win" are defined
once on `MNKGame` and work in every k-in-a-row game.

**Views** inherit drawing. Each scene part (`grid`, `dice`, `matrix`, ...)
has a `View` subclass in `web/js/views/`. **Skins** subclass views again:
the Paper skin's `SketchGridView` extends `GridView` and only redraws the
lines by hand.

**Lenses** inherit analysis plumbing: a Python
{class}`~strategy_lab.lenses.base.Lens` produces JSON, a JS `LensView`
draws it.

## One request

The browser owns the session: game id, params, seed, seats and the action
log. Every request sends all of it:

1. The server rebuilds the state by replaying the log
   ({class}`~strategy_lab.core.session.Session`).
2. It applies the new action, then lets chance and bots move (one step, or
   until a human must act).
3. It returns the new log, the scene to draw, the legal moves and, when
   the game ended, what the result unlocked.

Because all randomness is a logged chance outcome, replay is exact. This
makes undo, replays from history and live rule editing free.
