# high-level

**Strategy Lab, rebuilt in Rust — as a terminal app, through three lenses.**

The parent project ([../README.md](../README.md)) is a browser app where you *design the
policy* instead of playing the moves. `high-level` is a from-scratch **Rust / ratatui**
rebuild that keeps that idea and splits it into **three views of the same solved game** —
each a different way of "solving" it:

```
┌ 1 Strategy ──────────┬ 2 Value-RL ──────────┬ 3 Symmetry ──────────┐
│ discover & stack the │ a value function the │ fold the game by its │
│ rule cards, by hand  │ machine LEARNS by    │ symmetry group to the│
│ — then simulate 100  │ self-play, converging│ few decisions that   │
│ games                │ to exact play        │ actually matter      │
└──────────────────────┴──────────────────────┴──────────────────────┘
```

Two games, switchable live with `g`:

- **Tic-Tac-Toe** — the dihedral group **D4** acts on the board: 9 opening moves collapse
  to **3** real choices, and the 5478 reachable positions to **765**.
- **Nim (3-4-5)** — heaps are interchangeable (**S₃**), but the deep abstraction is the
  **nim-sum** (`A ⊕ B ⊕ C`): the whole position is one number, and the only decision is
  "can I make it zero?".

## Run it

```bash
cd high-level
cargo run                 # the interactive TUI
cargo run -- selftest     # headless: prints a symmetry/match/RL summary, renders every view
cargo test                # 40 tests (logic + UI render + tiny-terminal robustness)
```

> Built against Rust 1.75. One transitive crate needs an older pin, already captured in
> `Cargo.lock`: `cargo update -p unicode-segmentation --precise 1.10.1` (re-apply if the
> lockfile is ever regenerated).

The **Catan lens** talks to the real catanatron engine over a tiny HTTP bridge. catanatron
is pinned as a **git submodule** at `catanatron/` (upstream
[bcollazo/catanatron](https://github.com/bcollazo/catanatron)); fetch it, then start the
bridge in a second terminal:

```bash
git submodule update --init --recursive   # from the repo root (or clone --recurse-submodules)
./scripts/catan-server.sh                  # first run makes a venv, installs the submodule editable
```

The bridge (`catan-server/app.py`) serves `127.0.0.1:8000`; leave it running and `cargo
run` connects to it. Without it, the Catan view degrades to an error message and the other
views are unaffected.

## The three views

### 1 · Strategy — *discover* the cards, then stack them
A policy is an ordered stack of **PICK**/**AVOID** rule cards, read top to bottom each turn
(exactly the original engine's semantics). The twist: the cards start **hidden**. You
reveal them by

- **scouting** (`s`) — the lab simulates trials and surfaces the *highest-impact* card you
  haven't found yet, or
- **beating a bot** — win a match and you "study their stack", unlocking the cards they used.

Stack your discovered cards, pick an opponent (`b`), simulate **100 games** (`r`), and read
the win bars, momentum and streaks. Replay a sample game with `v`. With the right Tic-Tac-Toe
order (`Finish it → Block → Fork → Smother → Center → Mirror corner → Corner → Edge`) you
draw every game — the deterministic optimum, rediscovered by hand.

### 2 · Value-RL — *learn* a value function
A tabular value function `V(s) ∈ [-1, 1]` (value to the player to move) is **learned by
self-play** — ε-greedy behaviour, off-policy negamax backups in reverse along each episode,
with **exploring starts** for full coverage. Hit `space` to train live and watch:

- the **convergence chart** — mean error to the exact minimax values (`MAE`) falling toward 0,
- the **value heatmap** painted onto the board (per-move learned value, exact vs learned),
- `V(start) → 0.00` (a draw, for Tic-Tac-Toe), and `loss vs random → 0%`.

The exact values it converges *to* come from a memoised negamax `Solver` — the ground truth.

### 3 · Symmetry — abstract to the *core decision*
Fold the game by its symmetry group and the noise disappears:

- **Core decisions** — the legal moves grouped into symmetry-equivalent classes. The header
  reads `9 legal moves → 3 real decisions`; each class shows its size, exact value, and which
  is best.
- **Orbit** — the up-to-8 boards that are all literally the same position.
- **Reduction** — reachable → distinct-under-the-group, the factor, and a per-ply breakdown.
  This is *why* the value table in view 2 is small: symmetry does the compression.

Move around any position (`↑↓` pick a move, `⏎` play, `u` undo, `n` new board) — the Value
and Symmetry views share that board, so you can read the same position three ways.

## Keys

| | |
|---|---|
| `1` `2` `3` | switch view |
| `g` | switch game (Tic-Tac-Toe ↔ Nim) |
| `?` · `q` | help · quit |
| **Strategy** | `tab` focus · `↑↓` move · `⏎` add/remove · `[` `]` reorder · `s` scout · `b` opponent · `r` run 100 · `v` replay |
| **Value-RL** | `space` auto-train · `t` step · `R` reset · `↑↓` pick move · `⏎` play · `u` undo · `n` new |
| **Symmetry** | `↑↓` pick move · `⏎` play · `u` undo · `n` new board |

## Architecture

Pure logic is free of any terminal dependency, so all of it is unit-tested headlessly.
The `ui` layer is read-only over `App`/`Session`.

```
src/
  rng.rs        deterministic mulberry32 RNG (ported from the JS engine)
  game/
    mod.rs      the Game trait + UI-agnostic BoardSketch
    tictactoe.rs  rules · D4 group · cards · bots
    nim.rs        rules · S₃ group · nim-sum cards · bots
  cards.rs      Card / Rule (PICK & AVOID) — pure-function rules
  engine.rs     policy evaluation · 100-game match · stats · replay
  symmetry.rs   canonicalisation · orbits · move-classes · state-space analysis
  rl.rs         exact Solver (negamax) + QLearner (self-play value function)
  app.rs        all interactive state: Session<G> (per game) + App (chrome, input)
  ui/           ratatui rendering: chrome, board sketches, overlays + the 3 views
  selftest.rs   headless end-to-end check (also renders every view to a TestBackend)
  main.rs       terminal setup + event loop (auto-trains while idle)
```

Adding a third game is implementing the `Game` trait (rules + a symmetry group + a
`BoardSketch`) and a card list — the engine, RL, symmetry analysis and every generic UI
widget come for free.

## Tests

`cargo test` runs 40 tests:

- **logic** — RNG determinism; rules; D4/S₃ group closure; **5478→765** folding; perfect
  play draws / never loses; solver exactness; **Q-learner convergence**; symmetry-invariance
  of canonical key *and* value.
- **app** — scouting/discovery, 100-game accounting, beat-a-bot card stealing, training
  progress, explore/undo/reset, replay, game/tab switching, auto-train gating.
- **ui** — every view renders for both games with the expected text, overlays draw, and the
  layout survives absurd terminal sizes (8×4 … 200×60) without panicking.
