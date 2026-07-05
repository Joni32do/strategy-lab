//! high-level — Strategy Lab rebuilt in Rust.
//!
//! Three lenses on the same solved game:
//!   1. `cards`     — a human-readable heuristic policy you *discover* and stack.
//!   2. `rl`        — a value function the machine *learns* by self-play.
//!   3. `symmetry`  — the abstraction that collapses the game to its core decisions.
//!
//! The pure logic (everything except `app`/`ui`) is free of any terminal
//! dependency, so it is all unit-testable headlessly.

pub mod rng;
pub mod game;
pub mod catan;
pub mod cards;
pub mod engine;
pub mod rl;
pub mod symmetry;
pub mod app;
pub mod selftest;
pub mod ui;
