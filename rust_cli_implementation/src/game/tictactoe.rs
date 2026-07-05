//! Tic-Tac-Toe — the showcase. Fully solved, and rich in exactly the ways the
//! three views care about: a known-perfect card order, a value function that
//! provably converges to all-draws, and the dihedral group D4 acting on the
//! board (so the 9-way opening collapses to 3 real choices).

use super::{Game, Seat};
use crate::cards::{Card, CardKind, Rule};
use crate::rng::Rng;

pub struct TicTacToe;

/// `current` and `first` are seats (0 = you, 1 = opp). `first` only labels
/// X/O for display — whoever starts is X. Board cells hold the occupying seat.
#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub struct State {
    pub board: [Option<u8>; 9],
    pub current: u8,
    pub first: u8,
}

pub type Move = usize; // a cell index 0..9

const LINES: [[usize; 3]; 8] = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8], // rows
    [0, 3, 6], [1, 4, 7], [2, 5, 8], // cols
    [0, 4, 8], [2, 4, 6],            // diagonals
];
pub const CORNERS: [usize; 4] = [0, 2, 6, 8];
pub const EDGES: [usize; 4] = [1, 3, 5, 7];
const CELL_NAMES: [&str; 9] = [
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
];

/// D4: the 8 symmetries of the square, as cell permutations.
/// `new_board[i] = old_board[D4[g][i]]`.
pub const D4: [[usize; 9]; 8] = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8], // identity
    [6, 3, 0, 7, 4, 1, 8, 5, 2], // rotate 90° CW
    [8, 7, 6, 5, 4, 3, 2, 1, 0], // rotate 180°
    [2, 5, 8, 1, 4, 7, 0, 3, 6], // rotate 270° CW
    [2, 1, 0, 5, 4, 3, 8, 7, 6], // flip horizontal
    [6, 7, 8, 3, 4, 5, 0, 1, 2], // flip vertical
    [0, 3, 6, 1, 4, 7, 2, 5, 8], // transpose (main diagonal)
    [8, 5, 2, 7, 4, 1, 6, 3, 0], // anti-diagonal
];
const D4_LABELS: [&str; 8] = [
    "identity", "rotate 90°", "rotate 180°", "rotate 270°",
    "mirror ↔", "mirror ↕", "diagonal ⤢", "anti-diagonal ⤡",
];

pub fn opposite_corner(c: usize) -> Option<usize> {
    match c {
        0 => Some(8),
        2 => Some(6),
        6 => Some(2),
        8 => Some(0),
        _ => None,
    }
}

fn line_winner(b: &[Option<u8>; 9]) -> Option<u8> {
    for l in LINES {
        if let Some(p) = b[l[0]] {
            if b[l[1]] == Some(p) && b[l[2]] == Some(p) {
                return Some(p);
            }
        }
    }
    None
}

/// The completed line itself, for highlighting in the UI.
pub fn winning_line(b: &[Option<u8>; 9]) -> Option<[usize; 3]> {
    for l in LINES {
        if let Some(p) = b[l[0]] {
            if b[l[1]] == Some(p) && b[l[2]] == Some(p) {
                return Some(l);
            }
        }
    }
    None
}

/// Would `seat` win immediately by taking `cell`?
fn wins_now(b: &[Option<u8>; 9], cell: usize, seat: u8) -> bool {
    let mut t = *b;
    t[cell] = Some(seat);
    line_winner(&t) == Some(seat)
}

/// Cells that would complete a two-in-a-row for `seat` (open threats).
fn threat_squares(b: &[Option<u8>; 9], seat: u8) -> Vec<usize> {
    let mut res = vec![];
    for l in LINES {
        let mut mine = 0;
        let mut empty = None;
        let mut blocked = false;
        for &c in &l {
            match b[c] {
                Some(p) if p == seat => mine += 1,
                None => empty = Some(c),
                _ => blocked = true,
            }
        }
        if !blocked && mine == 2 {
            if let Some(e) = empty {
                res.push(e);
            }
        }
    }
    res
}

/// Does taking `cell` give `seat` two simultaneous threats (a fork)?
fn makes_fork(b: &[Option<u8>; 9], cell: usize, seat: u8) -> bool {
    let mut t = *b;
    t[cell] = Some(seat);
    threat_squares(&t, seat).len() >= 2
}

impl TicTacToe {
    pub fn mark(&self, s: &State, seat: u8) -> char {
        if seat == s.first {
            'X'
        } else {
            'O'
        }
    }
}

impl Game for TicTacToe {
    type State = State;
    type Move = Move;

    const ID: &'static str = "tictactoe";
    const NAME: &'static str = "Tic-Tac-Toe";
    const ICON: &'static str = "#";
    const TAGLINE: &'static str =
        "The 3×3 duel — mathematically solved. Re-solve it three ways.";

    fn initial(&self, _rng: &mut Rng, first: Seat) -> State {
        State {
            board: [None; 9],
            current: first as u8,
            first: first as u8,
        }
    }
    fn current(&self, s: &State) -> Seat {
        s.current as Seat
    }
    fn legal_moves(&self, s: &State) -> Vec<Move> {
        (0..9).filter(|&i| s.board[i].is_none()).collect()
    }
    fn apply(&self, s: &State, mv: Option<&Move>, _rng: &mut Rng) -> State {
        let mut n = s.clone();
        if let Some(&cell) = mv {
            n.board[cell] = Some(s.current);
        }
        n.current = 1 - s.current;
        n
    }
    fn is_terminal(&self, s: &State) -> bool {
        line_winner(&s.board).is_some() || s.board.iter().all(|c| c.is_some())
    }
    fn winner(&self, s: &State) -> Option<Seat> {
        line_winner(&s.board).map(|p| p as Seat)
    }
    fn max_turns(&self) -> u32 {
        9
    }

    fn key(&self, s: &State) -> u64 {
        let mut v: u64 = 0;
        for i in (0..9).rev() {
            let digit = match s.board[i] {
                None => 0,
                Some(0) => 1,
                _ => 2,
            };
            v = v * 3 + digit;
        }
        v * 2 + s.current as u64
    }

    fn group_order(&self) -> usize {
        8
    }
    fn group_label(&self, g: usize) -> String {
        D4_LABELS[g % 8].into()
    }
    fn transform(&self, s: &State, g: usize) -> State {
        let perm = &D4[g % 8];
        let mut board = [None; 9];
        for i in 0..9 {
            board[i] = s.board[perm[i]];
        }
        State {
            board,
            current: s.current,
            first: s.first,
        }
    }

    fn describe(&self, s: &State, mv: Option<&Move>, seat: Seat) -> String {
        match mv {
            Some(&cell) => format!(
                "places {} in the {} square",
                self.mark(s, seat as u8),
                CELL_NAMES[cell]
            ),
            None => "has no move".into(),
        }
    }
    fn move_label(&self, _s: &State, mv: &Move) -> String {
        CELL_NAMES[*mv].into()
    }
    fn sketch(&self, s: &State) -> super::BoardSketch {
        let win = winning_line(&s.board);
        let cells = (0..9)
            .map(|i| super::SketchCell {
                text: match s.board[i] {
                    Some(seat) => self.mark(s, seat).to_string(),
                    None => String::new(),
                },
                owner: s.board[i].map(|s| s as Seat),
                highlighted: win.map_or(false, |l| l.contains(&i)),
            })
            .collect();
        super::BoardSketch::Grid { cols: 3, cells }
    }
    fn move_cell(&self, _s: &State, mv: &Move) -> Option<usize> {
        Some(*mv)
    }
}

// --------------------------------------------------------------------------- //
// Strategy cards — the proven-perfect order is:
//   Finish it → Block → Fork → Smother forks → Center → Mirror corner →
//   Corner → Edge.  Discover them, stack them in that order, draw every game.
// --------------------------------------------------------------------------- //
pub fn cards() -> Vec<Card<TicTacToe>> {
    vec![
        Card {
            id: "win",
            name: "Finish it",
            glyph: "★",
            kind: CardKind::Pick,
            blurb: "If a move wins right now, play it.",
            rule: Rule::Pick(|_g: &TicTacToe, s: &State, cands: &[Move], seat: Seat, _rng: &mut Rng| {
                cands.iter().copied().find(|&c| wins_now(&s.board, c, seat as u8))
            }),
        },
        Card {
            id: "block",
            name: "Block the win",
            glyph: "▣",
            kind: CardKind::Pick,
            blurb: "If the opponent could win next, take that square first.",
            rule: Rule::Pick(|_g: &TicTacToe, s: &State, cands: &[Move], seat: Seat, _rng: &mut Rng| {
                let opp = 1 - seat as u8;
                cands.iter().copied().find(|&c| wins_now(&s.board, c, opp))
            }),
        },
        Card {
            id: "fork",
            name: "Build a fork",
            glyph: "Ψ",
            kind: CardKind::Pick,
            blurb: "Make two winning threats at once — only one can be blocked.",
            rule: Rule::Pick(|_g: &TicTacToe, s: &State, cands: &[Move], seat: Seat, _rng: &mut Rng| {
                cands.iter().copied().find(|&c| makes_fork(&s.board, c, seat as u8))
            }),
        },
        Card {
            id: "block-fork",
            name: "Smother forks",
            glyph: "▥",
            kind: CardKind::Pick,
            blurb: "Stop the opponent setting up a double threat.",
            rule: Rule::Pick(|_g: &TicTacToe, s: &State, cands: &[Move], seat: Seat, _rng: &mut Rng| {
                let opp = 1 - seat as u8;
                let me = seat as u8;
                let forks: Vec<usize> =
                    cands.iter().copied().filter(|&c| makes_fork(&s.board, c, opp)).collect();
                if forks.is_empty() {
                    return None;
                }
                if forks.len() == 1 {
                    return Some(forks[0]);
                }
                // Multiple fork squares: force a defence instead — make a
                // threat whose completion square is not itself a fork for them.
                for &c in cands {
                    let mut b = s.board;
                    b[c] = Some(me);
                    let comps = threat_squares(&b, me);
                    if !comps.is_empty() && comps.iter().all(|&e| !makes_fork(&b, e, opp)) {
                        return Some(c);
                    }
                }
                Some(forks[0])
            }),
        },
        Card {
            id: "center",
            name: "Take the center",
            glyph: "◎",
            kind: CardKind::Pick,
            blurb: "The middle sits on four lines — grab it.",
            rule: Rule::Pick(|_g: &TicTacToe, _s: &State, cands: &[Move], _seat: Seat, _rng: &mut Rng| {
                cands.iter().copied().find(|&c| c == 4)
            }),
        },
        Card {
            id: "opp-corner",
            name: "Mirror corner",
            glyph: "◈",
            kind: CardKind::Pick,
            blurb: "If the opponent holds a corner, take the one opposite. (A symmetry play.)",
            rule: Rule::Pick(|_g: &TicTacToe, s: &State, cands: &[Move], seat: Seat, _rng: &mut Rng| {
                let opp = 1 - seat as u8;
                for c in CORNERS {
                    if s.board[c] == Some(opp) {
                        if let Some(o) = opposite_corner(c) {
                            if cands.contains(&o) {
                                return Some(o);
                            }
                        }
                    }
                }
                None
            }),
        },
        Card {
            id: "corner",
            name: "Grab a corner",
            glyph: "◢",
            kind: CardKind::Pick,
            blurb: "Corners each sit on three lines — strong real estate.",
            rule: Rule::Pick(|_g: &TicTacToe, _s: &State, cands: &[Move], _seat: Seat, rng: &mut Rng| {
                let cs: Vec<usize> =
                    cands.iter().copied().filter(|c| CORNERS.contains(c)).collect();
                if cs.is_empty() {
                    None
                } else {
                    Some(*rng.choice(&cs))
                }
            }),
        },
        Card {
            id: "edge",
            name: "Take an edge",
            glyph: "─",
            kind: CardKind::Pick,
            blurb: "Settle for a side square.",
            rule: Rule::Pick(|_g: &TicTacToe, _s: &State, cands: &[Move], _seat: Seat, rng: &mut Rng| {
                let es: Vec<usize> =
                    cands.iter().copied().filter(|c| EDGES.contains(c)).collect();
                if es.is_empty() {
                    None
                } else {
                    Some(*rng.choice(&es))
                }
            }),
        },
    ]
}

/// Bot personas, weakest → strongest. The last is provably unbeatable.
pub fn bots() -> Vec<(&'static str, &'static str, u8, &'static str, Vec<&'static str>)> {
    vec![
        ("Randy Rookie", "random", 1, "Plays completely random squares.", vec![]),
        ("Greedy Gus", "greedy", 2, "Takes a win when he sees one. Otherwise, vibes.", vec!["win"]),
        (
            "Careful Carla",
            "careful",
            3,
            "Wins when possible and blocks your wins — but has no plan.",
            vec!["win", "block"],
        ),
        (
            "Minnie Max",
            "perfect",
            4,
            "Textbook perfect. She cannot be beaten — only drawn.",
            vec!["win", "block", "fork", "block-fork", "center", "opp-corner", "corner", "edge"],
        ),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_wins() {
        let mut b = [None; 9];
        b[0] = Some(0);
        b[1] = Some(0);
        assert!(wins_now(&b, 2, 0));
        assert!(!wins_now(&b, 5, 0));
    }

    #[test]
    fn d4_is_a_group_of_distinct_permutations() {
        // All 8 perms distinct, each a bijection, identity present.
        use std::collections::HashSet;
        let mut seen = HashSet::new();
        for g in 0..8 {
            let p = D4[g];
            let mut sorted = p;
            sorted.sort();
            assert_eq!(sorted, [0, 1, 2, 3, 4, 5, 6, 7, 8], "perm {g} not a bijection");
            assert!(seen.insert(p), "duplicate perm at {g}");
        }
        assert_eq!(D4[0], [0, 1, 2, 3, 4, 5, 6, 7, 8]);
    }

    #[test]
    fn d4_closed_under_composition() {
        // Composing any two elements yields another element of the set.
        use std::collections::HashSet;
        let set: HashSet<[usize; 9]> = D4.iter().copied().collect();
        for a in &D4 {
            for b in &D4 {
                let mut comp = [0usize; 9];
                for i in 0..9 {
                    comp[i] = a[b[i]];
                }
                assert!(set.contains(&comp), "composition escaped the group");
            }
        }
    }

    #[test]
    fn fork_detection() {
        // X at corners 0 and 8: playing 2 makes two threats (row 0, col 2).
        let mut b = [None; 9];
        b[0] = Some(0);
        b[8] = Some(0);
        assert!(makes_fork(&b, 2, 0));
    }
}
