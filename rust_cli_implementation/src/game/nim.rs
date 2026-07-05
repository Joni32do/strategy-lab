//! Nim (3 heaps, normal play) — the purest "abstract it to one number" game.
//!
//! Heaps are interchangeable (the symmetry group is S₃, permuting the three
//! heaps), but the *deep* abstraction is the Sprague–Grundy nim-sum: the entire
//! position collapses to `h0 XOR h1 XOR h2`, and the only decision that matters
//! is "can I move to nim-sum 0?". The symmetry view makes that visible.

use super::{Game, Seat};
use crate::cards::{Card, CardKind, Rule};
use crate::rng::Rng;

pub struct Nim;

pub const HEAPS: usize = 3;
pub const START: [u8; HEAPS] = [3, 4, 5]; // nim-sum 2 ≠ 0 ⇒ player to move wins
pub const HEAP_NAMES: [&str; HEAPS] = ["A", "B", "C"];

#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub struct State {
    pub heaps: [u8; HEAPS],
    pub current: u8,
}

/// (heap index, count removed ≥ 1).
pub type Move = (usize, u8);

/// S₃ — the six permutations of three heaps.
const S3: [[usize; 3]; 6] = [
    [0, 1, 2],
    [0, 2, 1],
    [1, 0, 2],
    [1, 2, 0],
    [2, 0, 1],
    [2, 1, 0],
];
const S3_LABELS: [&str; 6] = [
    "identity", "swap B,C", "swap A,B", "rotate A→B→C", "rotate A→C→B", "swap A,C",
];

pub fn nim_sum(heaps: &[u8; HEAPS]) -> u8 {
    heaps.iter().fold(0, |a, &h| a ^ h)
}

fn largest_heap(heaps: &[u8; HEAPS]) -> Option<usize> {
    (0..HEAPS).filter(|&i| heaps[i] > 0).max_by_key(|&i| heaps[i])
}

fn smallest_heap(heaps: &[u8; HEAPS]) -> Option<usize> {
    (0..HEAPS).filter(|&i| heaps[i] > 0).min_by_key(|&i| heaps[i])
}

impl Game for Nim {
    type State = State;
    type Move = Move;

    const ID: &'static str = "nim";
    const NAME: &'static str = "Nim";
    const ICON: &'static str = "≡";
    const TAGLINE: &'static str =
        "Three heaps, take from one. The whole game is a single XOR.";

    fn initial(&self, _rng: &mut Rng, first: Seat) -> State {
        State { heaps: START, current: first as u8 }
    }
    fn current(&self, s: &State) -> Seat {
        s.current as Seat
    }
    fn legal_moves(&self, s: &State) -> Vec<Move> {
        let mut m = vec![];
        for h in 0..HEAPS {
            for k in 1..=s.heaps[h] {
                m.push((h, k));
            }
        }
        m
    }
    fn apply(&self, s: &State, mv: Option<&Move>, _rng: &mut Rng) -> State {
        let mut n = s.clone();
        if let Some(&(h, k)) = mv {
            n.heaps[h] = n.heaps[h].saturating_sub(k);
        }
        n.current = 1 - s.current;
        n
    }
    fn is_terminal(&self, s: &State) -> bool {
        s.heaps.iter().all(|&h| h == 0)
    }
    fn winner(&self, s: &State) -> Option<Seat> {
        // Normal play: whoever takes the last object wins. When the board is
        // empty the player to move cannot move and has lost.
        if self.is_terminal(s) {
            Some(super::other(s.current as Seat))
        } else {
            None
        }
    }
    fn max_turns(&self) -> u32 {
        60
    }

    fn key(&self, s: &State) -> u64 {
        let mut v: u64 = 0;
        for &h in &s.heaps {
            v = v * 16 + h as u64;
        }
        v * 2 + s.current as u64
    }

    fn group_order(&self) -> usize {
        6
    }
    fn group_label(&self, g: usize) -> String {
        S3_LABELS[g % 6].into()
    }
    fn transform(&self, s: &State, g: usize) -> State {
        let perm = &S3[g % 6];
        let mut heaps = [0u8; HEAPS];
        for i in 0..HEAPS {
            heaps[i] = s.heaps[perm[i]];
        }
        State { heaps, current: s.current }
    }

    fn describe(&self, _s: &State, mv: Option<&Move>, _seat: Seat) -> String {
        match mv {
            Some(&(h, k)) => format!(
                "takes {} from heap {}",
                k, HEAP_NAMES[h]
            ),
            None => "has no move".into(),
        }
    }
    fn move_label(&self, _s: &State, mv: &Move) -> String {
        format!("−{} from {}", mv.1, HEAP_NAMES[mv.0])
    }
    fn sketch(&self, s: &State) -> super::BoardSketch {
        super::BoardSketch::Heaps {
            labels: HEAP_NAMES.iter().map(|h| h.to_string()).collect(),
            counts: s.heaps.iter().map(|&h| h as u32).collect(),
            max: *START.iter().max().unwrap() as u32,
        }
    }
}

pub fn cards() -> Vec<Card<Nim>> {
    vec![
        Card {
            id: "xor",
            name: "Balance",
            glyph: "⊕",
            kind: CardKind::Pick,
            blurb: "Move to nim-sum 0 — the proven winning play, when it exists.",
            rule: Rule::Pick(|_g: &Nim, s: &State, cands: &[Move], _seat: Seat, _rng: &mut Rng| {
                cands.iter().copied().find(|&(h, k)| {
                    let mut t = s.heaps;
                    t[h] -= k;
                    nim_sum(&t) == 0
                })
            }),
        },
        Card {
            id: "empty",
            name: "Clear a heap",
            glyph: "∅",
            kind: CardKind::Pick,
            blurb: "Wipe out the smallest heap — fewer heaps, simpler board.",
            rule: Rule::Pick(|_g: &Nim, s: &State, cands: &[Move], _seat: Seat, _rng: &mut Rng| {
                smallest_heap(&s.heaps).map(|h| (h, s.heaps[h])).filter(|m| cands.contains(m))
            }),
        },
        Card {
            id: "big",
            name: "Hit the biggest",
            glyph: "▰",
            kind: CardKind::Pick,
            blurb: "Empty the largest heap in one greedy swing.",
            rule: Rule::Pick(|_g: &Nim, s: &State, cands: &[Move], _seat: Seat, _rng: &mut Rng| {
                largest_heap(&s.heaps).map(|h| (h, s.heaps[h])).filter(|m| cands.contains(m))
            }),
        },
        Card {
            id: "one",
            name: "Nibble",
            glyph: "·",
            kind: CardKind::Pick,
            blurb: "Take a single object from the largest heap. Cautious.",
            rule: Rule::Pick(|_g: &Nim, s: &State, cands: &[Move], _seat: Seat, _rng: &mut Rng| {
                largest_heap(&s.heaps).map(|h| (h, 1)).filter(|m| cands.contains(m))
            }),
        },
        Card {
            id: "balanced",
            name: "Stay balanced",
            glyph: "⊘",
            kind: CardKind::Avoid,
            blurb: "Veto any move that leaves a non-zero nim-sum (when one is avoidable).",
            rule: Rule::Avoid(|_g: &Nim, s: &State, mv: &Move, _seat: Seat| {
                let (h, k) = *mv;
                let mut t = s.heaps;
                t[h] -= k;
                nim_sum(&t) != 0
            }),
        },
    ]
}

pub fn bots() -> Vec<(&'static str, &'static str, u8, &'static str, Vec<&'static str>)> {
    vec![
        ("Random Randy", "random", 1, "Removes a random amount from a random heap.", vec![]),
        ("Greedy Greg", "greedy", 2, "Always empties the biggest heap. Bold.", vec!["big"]),
        (
            "Tidy Tina",
            "tidy",
            3,
            "Clears small heaps, then swings at the big one.",
            vec!["empty", "big"],
        ),
        (
            "Grandmaster Grundy",
            "perfect",
            4,
            "Plays the nim-sum. From a winning position, never loses.",
            vec!["xor", "balanced", "big"],
        ),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rng::Rng;

    #[test]
    fn nim_sum_of_start() {
        assert_eq!(nim_sum(&START), 2); // 3 ^ 4 ^ 5 = 2
    }

    #[test]
    fn s3_distinct_bijections() {
        use std::collections::HashSet;
        let mut seen = HashSet::new();
        for p in S3 {
            let mut s = p;
            s.sort();
            assert_eq!(s, [0, 1, 2]);
            assert!(seen.insert(p));
        }
    }

    #[test]
    fn terminal_and_winner() {
        let g = Nim;
        let s = State { heaps: [0, 0, 0], current: 0 };
        assert!(g.is_terminal(&s));
        // player 0 to move but cannot — player 1 took the last object and won.
        assert_eq!(g.winner(&s), Some(1));
    }

    #[test]
    fn balance_move_exists_from_start() {
        // From [3,4,5] (nim-sum 2) a zeroing move exists: take 2 from heap C → [3,4,3].
        let g = Nim;
        let s = g.initial(&mut Rng::new(1), 0);
        let moves = g.legal_moves(&s);
        let zeroing = moves.iter().any(|&(h, k)| {
            let mut t = s.heaps;
            t[h] -= k;
            nim_sum(&t) == 0
        });
        assert!(zeroing);
    }
}
