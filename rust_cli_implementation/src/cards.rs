//! Strategy cards: the human-readable policy primitive.
//!
//! A policy is an ordered *stack* of cards, read top to bottom each turn:
//!   * a PICK card may choose a move from the current candidates,
//!   * an AVOID card vetoes candidates for the cards below it
//!     (but never vetoes *every* candidate).
//! The first PICK that decides, decides. If none do: a random legal move.

use crate::game::{Game, Seat};
use crate::rng::Rng;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum CardKind {
    Pick,
    Avoid,
}

impl CardKind {
    pub fn tag(self) -> &'static str {
        match self {
            CardKind::Pick => "PICK",
            CardKind::Avoid => "AVOID",
        }
    }
}

/// A rule is a pure function — no captured state — so cards are plain data.
pub enum Rule<G: Game> {
    Pick(fn(&G, &G::State, &[G::Move], Seat, &mut Rng) -> Option<G::Move>),
    Avoid(fn(&G, &G::State, &G::Move, Seat) -> bool),
}

pub struct Card<G: Game> {
    pub id: &'static str,
    pub name: &'static str,
    pub glyph: &'static str,
    pub kind: CardKind,
    pub blurb: &'static str,
    pub rule: Rule<G>,
}

/// Resolve a list of card ids against a game's palette, preserving order.
pub fn resolve<'a, G: Game>(palette: &'a [Card<G>], ids: &[&str]) -> Vec<&'a Card<G>> {
    ids.iter()
        .filter_map(|id| palette.iter().find(|c| &c.id == id))
        .collect()
}
