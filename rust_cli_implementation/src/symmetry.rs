//! Symmetry: the abstraction lens.
//!
//! Every game carries a symmetry group (`Game::transform`). Folding states by
//! that group collapses a huge tree into the handful of *essentially different*
//! positions — and collapses a turn's many legal moves into the few that are
//! genuinely distinct decisions. This module is pure structure: optimal values
//! are supplied separately by the solver, so it has no dependency on the RL code.

use crate::game::Game;
use crate::rng::Rng;
use std::collections::{HashMap, HashSet, VecDeque};

/// Smallest key over a state's symmetry orbit — its canonical fingerprint.
pub fn canonical_key<G: Game>(g: &G, s: &G::State) -> u64 {
    let mut best = g.key(s);
    for grp in 1..g.group_order() {
        best = best.min(g.key(&g.transform(s, grp)));
    }
    best
}

/// The canonical representative state (the orbit member with the smallest key).
pub fn canonical_state<G: Game>(g: &G, s: &G::State) -> G::State {
    let mut best_key = g.key(s);
    let mut best = s.clone();
    for grp in 1..g.group_order() {
        let t = g.transform(s, grp);
        let k = g.key(&t);
        if k < best_key {
            best_key = k;
            best = t;
        }
    }
    best
}

/// A distinct member of a state's orbit and the group element that produced it.
pub struct OrbitMember<G: Game> {
    pub group_index: usize,
    pub state: G::State,
}

/// The distinct states symmetric to `s` (deduplicated by key, includes `s`).
pub fn orbit<G: Game>(g: &G, s: &G::State) -> Vec<OrbitMember<G>> {
    let mut seen = HashSet::new();
    let mut out = vec![];
    for grp in 0..g.group_order() {
        let t = g.transform(s, grp);
        let k = g.key(&t);
        if seen.insert(k) {
            out.push(OrbitMember { group_index: grp, state: t });
        }
    }
    out
}

/// A class of legal moves that are equivalent under symmetry — i.e. one real
/// decision. The size of `members` is how many board cells "look different but
/// aren't". This is the heart of the symmetry view.
pub struct MoveClass<G: Game> {
    pub representative: G::Move,
    pub members: Vec<G::Move>,
    pub after_canonical: G::State,
    pub after_key: u64,
}

/// Group the legal moves of `s` into symmetry-equivalent decision classes.
/// Two moves are equivalent iff their resulting positions are symmetric.
pub fn move_classes<G: Game>(g: &G, s: &G::State) -> Vec<MoveClass<G>> {
    let mut dummy = Rng::new(0);
    let mut classes: Vec<MoveClass<G>> = vec![];
    for mv in g.legal_moves(s) {
        let after = g.apply(s, Some(&mv), &mut dummy);
        let key = canonical_key(g, &after);
        if let Some(c) = classes.iter_mut().find(|c| c.after_key == key) {
            c.members.push(mv);
        } else {
            classes.push(MoveClass {
                representative: mv.clone(),
                members: vec![mv],
                after_canonical: canonical_state(g, &after),
                after_key: key,
            });
        }
    }
    classes
}

/// State-space reduction statistics, gathered by BFS over the reachable tree.
/// Only meaningful for deterministic games (both of ours are).
pub struct SymStats {
    pub reachable: usize,
    pub canonical: usize,
    pub terminal: usize,
    pub group_order: usize,
    /// (ply, reachable_at_ply, canonical_at_ply)
    pub by_depth: Vec<(usize, usize, usize)>,
}

impl SymStats {
    pub fn reduction(&self) -> f64 {
        if self.canonical == 0 {
            1.0
        } else {
            self.reachable as f64 / self.canonical as f64
        }
    }
}

/// BFS the whole reachable game graph and count raw vs. canonical states.
pub fn analyze<G: Game>(g: &G) -> SymStats {
    let mut dummy = Rng::new(0);
    let start = g.initial(&mut dummy, crate::game::YOU);

    let mut reachable: HashSet<u64> = HashSet::new();
    let mut canonical: HashSet<u64> = HashSet::new();
    let mut terminal = 0usize;
    let mut depth_raw: HashMap<usize, HashSet<u64>> = HashMap::new();
    let mut depth_can: HashMap<usize, HashSet<u64>> = HashMap::new();

    let mut queue: VecDeque<(G::State, usize)> = VecDeque::new();
    let mut enqueued: HashSet<u64> = HashSet::new();

    enqueued.insert(g.key(&start));
    queue.push_back((start, 0));

    while let Some((s, depth)) = queue.pop_front() {
        let k = g.key(&s);
        let ck = canonical_key(g, &s);
        reachable.insert(k);
        canonical.insert(ck);
        depth_raw.entry(depth).or_default().insert(k);
        depth_can.entry(depth).or_default().insert(ck);

        if g.is_terminal(&s) {
            terminal += 1;
            continue;
        }
        for mv in g.legal_moves(&s) {
            let child = g.apply(&s, Some(&mv), &mut dummy);
            let ckey = g.key(&child);
            if enqueued.insert(ckey) {
                queue.push_back((child, depth + 1));
            }
        }
    }

    let max_depth = depth_raw.keys().copied().max().unwrap_or(0);
    let by_depth = (0..=max_depth)
        .map(|d| {
            (
                d,
                depth_raw.get(&d).map_or(0, |s| s.len()),
                depth_can.get(&d).map_or(0, |s| s.len()),
            )
        })
        .collect();

    SymStats {
        reachable: reachable.len(),
        canonical: canonical.len(),
        terminal,
        group_order: g.group_order(),
        by_depth,
    }
}

/// Every non-terminal canonical state reachable from the start — the exact
/// domain of the value table. Used by the RL view to measure convergence.
pub fn enumerate_canonical<G: Game>(g: &G) -> Vec<G::State> {
    let mut dummy = Rng::new(0);
    let start = g.initial(&mut dummy, crate::game::YOU);
    let mut seen_canon: HashSet<u64> = HashSet::new();
    let mut out = vec![];
    let mut enqueued: HashSet<u64> = HashSet::new();
    let mut queue: VecDeque<G::State> = VecDeque::new();
    enqueued.insert(g.key(&start));
    queue.push_back(start);

    while let Some(s) = queue.pop_front() {
        if !g.is_terminal(&s) {
            let ck = canonical_key(g, &s);
            if seen_canon.insert(ck) {
                out.push(canonical_state(g, &s));
            }
            for mv in g.legal_moves(&s) {
                let child = g.apply(&s, Some(&mv), &mut dummy);
                if enqueued.insert(g.key(&child)) {
                    queue.push_back(child);
                }
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::{Game, Nim, TicTacToe};
    use crate::rl::Solver;

    #[test]
    fn ttt_reachable_and_canonical_counts() {
        // The classic numbers: 5478 reachable positions, 765 under D4.
        let stats = analyze(&TicTacToe);
        assert_eq!(stats.reachable, 5478, "reachable tic-tac-toe states");
        assert_eq!(stats.canonical, 765, "distinct under the dihedral group");
    }

    #[test]
    fn ttt_opening_has_three_real_choices() {
        // 9 first moves collapse to {corner, edge, center}.
        let g = TicTacToe;
        let mut r = Rng::new(0);
        let s = g.initial(&mut r, 0);
        let classes = move_classes(&g, &s);
        assert_eq!(classes.len(), 3, "opening collapses to 3 classes");
        let mut sizes: Vec<usize> = classes.iter().map(|c| c.members.len()).collect();
        sizes.sort();
        assert_eq!(sizes, vec![1, 4, 4], "center(1), edges(4), corners(4)");
    }

    #[test]
    fn ttt_orbit_of_empty_is_one() {
        let g = TicTacToe;
        let mut r = Rng::new(0);
        let s = g.initial(&mut r, 0);
        // The empty board is fixed by all 8 symmetries → orbit size 1.
        assert_eq!(orbit(&g, &s).len(), 1);
    }

    #[test]
    fn nim_symmetry_reduces_states() {
        let stats = analyze(&Nim);
        assert!(stats.canonical < stats.reachable, "S₃ must collapse heap orderings");
        assert_eq!(stats.group_order, 6);
    }

    #[test]
    fn canonical_key_and_value_are_symmetry_invariant() {
        // Build an asymmetric mid-game board, then check every symmetric image
        // shares the canonical key *and* the exact value.
        let g = TicTacToe;
        let mut r = Rng::new(3);
        let mut s = g.initial(&mut r, 0);
        for mv in [0usize, 4, 1] {
            s = g.apply(&s, Some(&mv), &mut r);
        }
        let ck = canonical_key(&g, &s);
        let mut solver = Solver::new();
        let v = solver.value(&g, &s);
        for grp in 0..g.group_order() {
            let t = g.transform(&s, grp);
            assert_eq!(canonical_key(&g, &t), ck, "canonical key invariant under D4");
            assert_eq!(solver.value(&g, &t), v, "value invariant under D4");
        }
    }

    #[test]
    fn move_classes_cover_every_legal_move() {
        // Across a played-out line, the symmetry classes always partition the moves.
        let g = Nim;
        let mut r = Rng::new(11);
        let mut s = g.initial(&mut r, 0);
        for _ in 0..3 {
            if g.is_terminal(&s) {
                break;
            }
            let classes = move_classes(&g, &s);
            let covered: usize = classes.iter().map(|c| c.members.len()).sum();
            assert_eq!(covered, g.legal_moves(&s).len(), "classes partition the moves");
            let mv = g.legal_moves(&s)[0].clone();
            s = g.apply(&s, Some(&mv), &mut r);
        }
    }
}
