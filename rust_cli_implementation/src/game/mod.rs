//! The `Game` abstraction every view shares.
//!
//! A game is a deterministic-or-chance, two-seat, zero-sum, alternating-turn
//! contest. Seat 0 is always *you*, seat 1 the *opponent*. The trait exposes
//! exactly what the three lenses need:
//!
//!   * rules        (`initial`/`legal_moves`/`apply`/`winner` …) — for the card engine,
//!   * a compact `key`  — for the value-function table & exact search,
//!   * a symmetry group (`group_order`/`transform`) — for the abstraction view.
//!
//! Concrete games live in submodules and stay free of any UI concern.

use crate::rng::Rng;

pub mod nim;
pub mod tictactoe;

pub use nim::Nim;
pub use tictactoe::TicTacToe;

/// A player. There are always exactly two.
pub type Seat = usize;
pub const YOU: Seat = 0;
pub const OPP: Seat = 1;

pub fn other(seat: Seat) -> Seat {
    1 - seat
}

pub trait Game: Sized + 'static {
    type State: Clone + PartialEq + Eq + std::hash::Hash + std::fmt::Debug;
    type Move: Clone + PartialEq + Eq + std::fmt::Debug;

    const ID: &'static str;
    const NAME: &'static str;
    const ICON: &'static str;
    /// One-line "what is this game" for the lab header.
    const TAGLINE: &'static str;

    // ---- rules ---------------------------------------------------------- //
    fn initial(&self, rng: &mut Rng, first: Seat) -> Self::State;
    fn current(&self, s: &Self::State) -> Seat;
    fn legal_moves(&self, s: &Self::State) -> Vec<Self::Move>;
    /// Pure transition. `mv == None` means "pass" (no legal move).
    fn apply(&self, s: &Self::State, mv: Option<&Self::Move>, rng: &mut Rng) -> Self::State;
    fn is_terminal(&self, s: &Self::State) -> bool;
    /// Winning seat, or `None` for a draw / undecided.
    fn winner(&self, s: &Self::State) -> Option<Seat>;
    fn max_turns(&self) -> u32 {
        1000
    }
    fn timeout_winner(&self, _s: &Self::State) -> Option<Seat> {
        None
    }

    // ---- value-function / search support -------------------------------- //
    /// Collision-free key for a *position to move* (board geometry + side).
    /// Two states with the same key are treated as the same node.
    fn key(&self, s: &Self::State) -> u64;
    /// No chance elements ⇒ exact minimax & afterstate value learning apply.
    fn deterministic(&self) -> bool {
        true
    }

    // ---- symmetry support ----------------------------------------------- //
    /// Size of the symmetry group acting on states (element 0 == identity).
    fn group_order(&self) -> usize {
        1
    }
    /// Human label for group element `g` (e.g. "rot 90°", "sort heaps").
    fn group_label(&self, _g: usize) -> String {
        "identity".into()
    }
    /// Apply group element `g`. Must keep `current`/turn semantics intact.
    fn transform(&self, s: &Self::State, _g: usize) -> Self::State {
        s.clone()
    }

    // ---- presentation --------------------------------------------------- //
    /// Replay/log caption for a move, *without* the actor ("takes the center").
    fn describe(&self, s: &Self::State, mv: Option<&Self::Move>, seat: Seat) -> String;
    /// Short label for a single move, used in the symmetry "core decision" list.
    fn move_label(&self, s: &Self::State, mv: &Self::Move) -> String;
    /// A UI-agnostic picture of a position, so the terminal layer can draw any
    /// game without knowing its internals.
    fn sketch(&self, s: &Self::State) -> BoardSketch;
    /// Which sketch cell a grid move lands on (for value overlays). `None` for
    /// non-grid games like Nim.
    fn move_cell(&self, _s: &Self::State, _mv: &Self::Move) -> Option<usize> {
        None
    }
}

/// One square of a board sketch.
#[derive(Clone)]
pub struct SketchCell {
    pub text: String,
    pub owner: Option<Seat>,
    pub highlighted: bool,
}

/// A renderer-friendly snapshot of a position.
#[derive(Clone)]
pub enum BoardSketch {
    Grid {
        cols: usize,
        cells: Vec<SketchCell>,
    },
    Heaps {
        labels: Vec<String>,
        counts: Vec<u32>,
        max: u32,
    },
}

/// Terminal value for the player *to move* at `s`, in [-1, 1].
/// +1 win, 0 draw, -1 loss. (For TTT/Nim the player to move at a decided
/// terminal has just lost, so this is typically -1.)
pub fn terminal_value<G: Game>(g: &G, s: &G::State) -> f64 {
    match g.winner(s) {
        Some(w) => {
            if w == g.current(s) {
                1.0
            } else {
                -1.0
            }
        }
        None => 0.0,
    }
}
