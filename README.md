# Strategy Lab

**Don't play the game. Solve it.**

A small web app where you don't play classic board games move by move — instead you
**design the strategy** that plays them. Build a policy out of simple rule cards, pick a
bot opponent, simulate **100 games**, and read the statistics. Whoever's policy wins more
games wins the match.

The point: discover for yourself *how much strategy a game actually has*. For some games
there are predefined games, e.g. for Tic-Tac-Toe optimal strategies exist. The way a strategy is
defined is non-trivial for the most cases.

*Still under activ developpment.*

## Available Games

- **Tic-Tac-Toe** — fully solved. With the right card order you find the deterministic
  optimal policy: 100 draws against perfect play, and nothing can do better.
- **Snakes & Ladders** *(pick-a-die variant)* — almost pure luck. Even perfect choices
  only nudge the odds. Realizing that is the insight.
- **Mensch ärgere dich nicht** — the interesting middle ground: dice keep it noisy, but
  priorities (capture, enter, stay out of reach) shift the odds dramatically.
- **Monopoly** — the dice turns run automatically; your policy answers the three
  questions that matter: buy it? build on it? pay your way out of jail? Simplified:
  no auctions/trading/mortgages (forced half-price sales instead), max 4 houses, an
  approximated rent curve, 60 rounds then net worth decides. Spoiler from the
  simulations: without trading, every sensible buying policy lands within a few
  percent — the dice own this board.
- **Settlers of Catan** — runs on the **real [catanatron](https://github.com/bcollazo/catanatron)
  engine**, not a hand-rolled reimplementation. The browser is a thin client over a small
  Flask wrapper (`server/`); catanatron computes every rule, move and tick. This unlocks
  the full game — development cards, **player-to-player trading**, the lot — and a richer,
  more interactive strategy interface (see [Catan Lab](#catan-lab) below).

## Getting started

The card-stack games (Tic-Tac-Toe, Snakes, Mädn, Monopoly) are pure client-side JS —
double-click, e.g.
```bash
open index.html
```

**Catan** needs its engine, which is pinned as a **git submodule** at `catanatron/`
(upstream [bcollazo/catanatron](https://github.com/bcollazo/catanatron)). Fetch it before
running — either clone with `--recurse-submodules`, or, in an existing checkout:

```bash
git submodule update --init catanatron
```

Dependencies (that catanatron submodule + Flask) are declared in `pyproject.toml` and
managed with [uv](https://docs.astral.sh/uv/); one command serves both the static app
*and* the catanatron API:

```bash
cd strategy-lab
uv run python server/app.py           # http://localhost:8000  → Catan Lab
```

`uv run` creates the `.venv` and installs everything on first use (catanatron is wired as
an editable path dependency on the submodule, so the engine source under `catanatron/`
drives every rule). Run `uv sync` first if you'd rather set the environment up ahead of
time.

### Tests

```bash
node test/smoke.js                        # JS games (engine + card logic)
uv run python server/test_policy.py       # the trading policy (metric, veto, symmetry)
```

<a name="catan-lab"></a>

## Catan Lab — (In development)

Open `catan.html` (or the Catan card on the home page). The premise is the same as the rest of
Strategy Lab — *design the policy, don't play the moves* — but here the policy is a
**parameterised value/trade function** instead of a card stack, and the rules come from
catanatron.

Your bot plays a catanatron **base brain** for building (`VALUE` by default, or
`ALPHABETA` search), and trades through a **state-dependent brain** that is the point of
this lab:

- **A position-strength metric** `strength(player) ∈ [0,1]` — the same function for every
  seat (a relabelling symmetry), blending closeness-to-victory, production and reach. This
  is what "how strong is this position" means, derived from catanatron's own features.
- **A non-linear trade coefficient** `λ(opponent_strength)`. Every swap is judged by
  `net = my_gain − λ · their_gain`. λ is ~0 against a weak rival (pure self-interest) and
  rises (logistic) as the rival gets strong, so you stop handing value to the leader — and
  a **hard veto** refuses *any* trade with a player within N VP of winning.
- **Symmetry compression**: decisions key off *relative* quantities, not absolute hands.
  "If the trade partner is 2 VP ahead, demand ~1 extra resource" is literally the
  `premium_per_vp` term, so equivalent positions get equivalent behaviour.
- **A blocking preference** `block_weight` — with the `VALUE` brain, candidate builds are
  re-ranked by how many expansion nodes they deny an opponent, so the bot will "build a
  road/settlement to block" when the knob is up. Zero leaves the pure value function; it
  never overrides a game-winning move.

Three interactive views:

- **Metric & trade tuner** — sliders for every weight and λ-shape parameter, with the
  coefficient curve redrawn live, plus a one-click batch simulation (win bars + trade
  tally) against any catanatron opponent
  (`RANDOM`/`WEIGHTED`/`VALUE`/`ALPHABETA`/`MCTS`/`TRADER`).
- **Decision boundary explorer** — the accept-a-trade rule is a surface over several inputs
  (opponent VP, your VP, opponent strength, each side's gain). Pick any two as axes and the
  rest are held fixed; the surface is drawn as an interpolated heatmap of the deal's *slack*
  (net − required), with the accept/refuse boundary as a contour and the hard veto hatched.
  Preset "views" collapse the n-dimensional rule onto a chosen pair; every tuner slider
  reshapes it live.
- **Step-through play** — watch the policy decide ply-by-ply on a rendered board, every
  move annotated with its reasoning; trades expand to show both players' strength, λ, the
  gains, and the accept / reject / **veto** decision.

The policy lives in `server/policy.py` (≈ a Catanatron `Player`); no Catan rules are
reimplemented anywhere in this repo.

## How a match works

1. **Build your strategy** — a *priority list* of rule cards, read top to bottom each turn:
   - **PICK** cards choose a move (e.g. "Finish it", "Headhunter").
   - **AVOID** cards veto candidate moves for the cards below (e.g. "Snake dodger") —
     unless that would veto everything.
   - The first card that can decide, decides. If none can: a random legal move.
2. **Pick a bot** — four personas per game, from random rookie to near-optimal. The bot's
   stack is shown openly: study it, steal from it.
3. **Simulate** — 100 games, starting player alternating. Every game gets its own RNG
   seed, so any individual game can be re-simulated deterministically for the replay
   viewer.
4. **Read the stats** — win bars, momentum chart (cumulative lead), streaks,
   first-mover split, a game-specific insight, and watchable sample replays.

## Architecture

```
index.html               script tags define which card-stack games are loaded
css/style.css            shared theme;  css/catan-lab.css  styles the Catan Lab
js/engine.js             policy evaluation + match simulation (game-agnostic, DOM-free)
js/games/*.js            one self-registering file per card-stack game
js/ui.js                 home gallery, lab, charts, replay viewer, persistence
test/smoke.js            headless Node tests of engine + card-stack games

catan.html               the Catan Lab page (thin client; needs the Flask server)
js/catan-lab.js          tuner + live λ curve + step-through board (talks to /api)
js/games/catan-board.js  generated board geometry (see tools/dump_catan_board.py)
server/app.py            Flask wrapper around catanatron (simulate / game / tick / defaults)
server/policy.py         the position metric + non-linear trade coefficient + Player
server/test_policy.py    metric symmetry, leader-veto, real-game trade tests
tools/                   board-geometry generator (needs the cloned catanatron repo)
catanatron/              git submodule (bcollazo/catanatron) — the engine, installed
                         editable; drives all Catan rules
pyproject.toml           uv project: Flask + catanatron (editable path dep); uv.lock pins it
rust_cli_implementation/ an alternative take: a Rust TUI over the same catanatron bridge
                         (has its own catanatron submodule + catan-server) — see its README
```

The engine and game files never touch the DOM except inside `renderState`, so all game
logic runs headless under Node for testing.

## Adding a game

Create `js/games/yourgame.js`, call `StrategyLab.registerGame({...})`, and add a script
tag in `index.html`. The interface:

| Field | Meaning |
| --- | --- |
| `id, name, icon, level, tagline` | gallery metadata |
| `rules` | the card palette: `{ id, name, icon, desc, kind }` plus `pick(state, candidates, seat, rng) → move\|null` for `kind:'pick'`, or `avoid(state, move, seat) → bool` for `kind:'avoid'` |
| `botPresets` | `{ id, name, icon, stars, desc, ruleIds }` — ordered rule ids |
| `initialState(rng, firstSeat)` | seats are always 0 = human, 1 = bot; pre-roll dice into the state if the game has chance |
| `currentPlayer(state)` / `legalMoves(state)` | a turn = one decision; return `[]` to pass |
| `applyMove(state, move, rng)` | **pure** — return a new state (use `StrategyLab.clone`), handle `move === null` as a pass, pre-roll the next dice |
| `isTerminal(state)` / `winner(state)` | winner returns seat or `null` for a draw |
| `maxTurns` + `timeoutWinner(state)` | safety cap for games that can stall |
| `describeMove(state, move, seat)` | replay caption, without the actor ("rolls 6 — …") |
| `renderState(state, el)` | draw the board into `el` (DOM/SVG, no interactivity needed) |
| `insight(stats)` | optional: game-specific takeaway shown on the results screen |

Keep states JSON-serializable (plain objects/arrays) — the engine deep-copies them with
`JSON.parse(JSON.stringify(...))` and replays rely on deterministic RNG, so never call
`Math.random()` inside game code; always use the passed `rng`.

Games with auto-resolving phases (Monopoly's dice turns, Catan's production) keep an
event `log` array inside the state and show it in `renderState`, so replays stay
readable even when several automatic events happen between two decisions.

### Rust CLI implementation
The pure `.js` framework seemed for me to be non-optimal, therefore I drafted an additional Rust,
CLI implementation, using three different policy management methods. Strategy, Value function,
Symmetry. For more details see [README](rust_cli_implementation/README.md).


### Roadmap ideas

- **The Game of Life**, **Backgammon** (a rich AVOID/PICK space: blots, primes, races).
- Catan: **learn** the metric weights and λ-curve (the coefficients are already a
  parameter vector — hill-climb or CMA-ES over win rate), and let you offer trades by hand
  in the step-through view.
- **Auto-tuner** — hill-climb over card orders and show *which* permutation of your
  cards performs best: policy iteration made visible.
- **Elo ladder** — persistent ratings for your strategies across sessions.
