//! The value-function lens.
//!
//! Two value functions over the same canonical states:
//!   * `Solver`   — exact minimax (negamax), the ground truth.
//!   * `QLearner` — a tabular value function *learned* from self-play, which we
//!     watch converge to the solver. Both store "value to the player to move"
//!     in [-1, 1] (+1 win, 0 draw, −1 loss), and both fold symmetric positions
//!     onto one entry via `symmetry::canonical_key`, so learning is 8× cheaper.

use crate::game::{terminal_value, Game};
use crate::rng::Rng;
use crate::symmetry::{canonical_key, enumerate_canonical};
use std::collections::HashMap;

// --------------------------------------------------------------------------- //
// Exact solver (negamax with a symmetry-folded transposition table)
// --------------------------------------------------------------------------- //
#[derive(Default)]
pub struct Solver {
    memo: HashMap<u64, f64>,
}

impl Solver {
    pub fn new() -> Self {
        Solver::default()
    }

    /// Exact value to the player to move at `s`.
    pub fn value<G: Game>(&mut self, g: &G, s: &G::State) -> f64 {
        if g.is_terminal(s) {
            return terminal_value(g, s);
        }
        let ck = canonical_key(g, s);
        if let Some(&v) = self.memo.get(&ck) {
            return v;
        }
        let mut dummy = Rng::new(0);
        let mut best = f64::NEG_INFINITY;
        for mv in g.legal_moves(s) {
            let child = g.apply(s, Some(&mv), &mut dummy);
            best = best.max(-self.value(g, &child));
        }
        self.memo.insert(ck, best);
        best
    }

    /// Exact value of each legal move (value to the player to move).
    pub fn move_values<G: Game>(&mut self, g: &G, s: &G::State) -> Vec<(G::Move, f64)> {
        let mut dummy = Rng::new(0);
        g.legal_moves(s)
            .into_iter()
            .map(|mv| {
                let child = g.apply(s, Some(&mv), &mut dummy);
                let v = -self.value(g, &child);
                (mv, v)
            })
            .collect()
    }
}

// --------------------------------------------------------------------------- //
// Learned value function (tabular, self-play, off-policy TD / value iteration)
// --------------------------------------------------------------------------- //
#[derive(Clone, Copy)]
pub struct Metric {
    pub episodes: usize,
    /// Mean |V_learned − V_exact| over all canonical non-terminal states.
    pub mae: f64,
    /// Learned value of the start position (→ 0 = draw, for tic-tac-toe).
    pub root_value: f64,
    pub epsilon: f64,
    /// Greedy policy vs. a random opponent, over the eval batch.
    pub eval_win: f64,
    pub eval_draw: f64,
    pub eval_loss: f64,
}

pub struct QLearner<G: Game> {
    pub table: HashMap<u64, f64>,
    pub alpha: f64,
    pub epsilon: f64,
    pub epsilon_min: f64,
    pub epsilon_decay: f64,
    pub episodes: usize,
    rng: Rng,
    domain: Vec<G::State>,
    optimal: Vec<f64>,
    pub history: Vec<Metric>,
}

impl<G: Game> QLearner<G> {
    pub fn new(g: &G, seed: u32) -> Self {
        let domain = enumerate_canonical(g);
        let mut solver = Solver::new();
        let optimal = domain.iter().map(|s| solver.value(g, s)).collect();
        let mut learner = QLearner {
            table: HashMap::new(),
            alpha: 0.4,
            epsilon: 1.0,
            // A high exploration floor on purpose: the whole state space is
            // tiny, so broad visitation matters more than exploitation here.
            epsilon_min: 0.30,
            epsilon_decay: 0.9997,
            episodes: 0,
            rng: Rng::new(seed),
            domain,
            optimal,
            history: vec![],
        };
        learner.snapshot(g);
        learner
    }

    pub fn domain_size(&self) -> usize {
        self.domain.len()
    }

    fn v_of(&self, g: &G, s: &G::State) -> f64 {
        if g.is_terminal(s) {
            terminal_value(g, s)
        } else {
            *self.table.get(&canonical_key(g, s)).unwrap_or(&0.0)
        }
    }

    /// Value to the mover of playing `mv` from `s` (= −value at the child).
    fn q(&self, g: &G, s: &G::State, mv: &G::Move) -> f64 {
        let mut dummy = Rng::new(0);
        let child = g.apply(s, Some(mv), &mut dummy);
        -self.v_of(g, &child)
    }

    fn greedy_target(&self, g: &G, s: &G::State) -> f64 {
        g.legal_moves(s)
            .iter()
            .map(|mv| self.q(g, s, mv))
            .fold(f64::NEG_INFINITY, f64::max)
    }

    /// The current greedy move (ties → first), for inspection and evaluation.
    pub fn greedy_move(&self, g: &G, s: &G::State) -> Option<G::Move> {
        g.legal_moves(s)
            .into_iter()
            .map(|mv| {
                let v = self.q(g, s, &mv);
                (mv, v)
            })
            .fold(None, |best: Option<(G::Move, f64)>, (mv, v)| match best {
                Some((_, bv)) if bv >= v => best,
                _ => Some((mv, v)),
            })
            .map(|(mv, _)| mv)
    }

    /// Learned value of each legal move — drives the value heatmap.
    pub fn move_values(&self, g: &G, s: &G::State) -> Vec<(G::Move, f64)> {
        g.legal_moves(s)
            .into_iter()
            .map(|mv| {
                let v = self.q(g, s, &mv);
                (mv, v)
            })
            .collect()
    }

    /// Run one self-play episode of off-policy value learning.
    ///
    /// Act first (ε-greedy), recording the path; then back the values up in
    /// *reverse*, so a terminal result propagates all the way to the opening in
    /// a single episode instead of leaking one ply at a time.
    fn run_episode(&mut self, g: &G, first: crate::game::Seat) {
        let mut dummy = Rng::new(self.rng.below(u32::MAX as usize) as u32);
        // Exploring starts: half the episodes begin from a random reachable
        // position, so even rarely-played states get backed up and the value
        // function converges *everywhere*, not just along well-played lines.
        let mut s = if !self.domain.is_empty() && self.rng.next_f64() < 0.5 {
            let idx = self.rng.below(self.domain.len());
            self.domain[idx].clone()
        } else {
            g.initial(&mut self.rng, first)
        };
        let mut trail: Vec<G::State> = vec![];
        let mut guard = 0u32;
        while !g.is_terminal(&s) && guard < g.max_turns() + 2 {
            guard += 1;
            trail.push(s.clone());
            let moves = g.legal_moves(&s);
            let mv = if self.rng.next_f64() < self.epsilon {
                self.rng.choice(&moves).clone()
            } else {
                self.greedy_move(g, &s).unwrap()
            };
            s = g.apply(&s, Some(&mv), &mut dummy);
        }
        for st in trail.iter().rev() {
            let target = self.greedy_target(g, st);
            let ck = canonical_key(g, st);
            let cur = *self.table.get(&ck).unwrap_or(&0.0);
            self.table.insert(ck, cur + self.alpha * (target - cur));
        }
        self.episodes += 1;
        self.epsilon = (self.epsilon * self.epsilon_decay).max(self.epsilon_min);
    }

    /// Advance the learner by `episodes` self-play games, then snapshot metrics.
    pub fn train(&mut self, g: &G, episodes: usize) {
        for i in 0..episodes {
            self.run_episode(g, i % 2);
        }
        self.snapshot(g);
    }

    fn mae(&self, g: &G) -> f64 {
        if self.domain.is_empty() {
            return 0.0;
        }
        let sum: f64 = self
            .domain
            .iter()
            .zip(&self.optimal)
            .map(|(s, &opt)| (self.v_of(g, s) - opt).abs())
            .sum();
        sum / self.domain.len() as f64
    }

    /// Evaluate the current greedy policy against a random opponent.
    fn eval_vs_random(&mut self, g: &G, games: usize) -> (f64, f64, f64) {
        let (mut win, mut draw, mut loss) = (0.0f64, 0.0, 0.0);
        for i in 0..games {
            let learner_seat = i % 2;
            let mut rng = Rng::new(crate::rng::game_seed(0xA17E, self.episodes * 131 + i));
            let mut s = g.initial(&mut rng, i % 2);
            let mut guard = 0;
            while !g.is_terminal(&s) && guard < g.max_turns() + 2 {
                guard += 1;
                let seat = g.current(&s);
                let mv = if seat == learner_seat {
                    self.greedy_move(g, &s)
                } else {
                    let moves = g.legal_moves(&s);
                    if moves.is_empty() {
                        None
                    } else {
                        Some(rng.choice(&moves).clone())
                    }
                };
                s = g.apply(&s, mv.as_ref(), &mut rng);
            }
            match g.winner(&s) {
                Some(w) if w == learner_seat => win += 1.0,
                Some(_) => loss += 1.0,
                None => draw += 1.0,
            }
        }
        let n = games.max(1) as f64;
        (win / n, draw / n, loss / n)
    }

    fn snapshot(&mut self, g: &G) {
        let mae = self.mae(g);
        let mut dummy = Rng::new(0);
        let root = g.initial(&mut dummy, crate::game::YOU);
        let root_value = self.greedy_target(g, &root);
        let (eval_win, eval_draw, eval_loss) = self.eval_vs_random(g, 200);
        self.history.push(Metric {
            episodes: self.episodes,
            mae,
            root_value,
            epsilon: self.epsilon,
            eval_win,
            eval_draw,
            eval_loss,
        });
    }

    pub fn reset(&mut self, g: &G, seed: u32) {
        self.table.clear();
        self.epsilon = 1.0;
        self.episodes = 0;
        self.rng = Rng::new(seed);
        self.history.clear();
        self.snapshot(g);
    }

    pub fn latest(&self) -> Metric {
        *self.history.last().unwrap()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::{Nim, TicTacToe};

    #[test]
    fn solver_says_ttt_is_a_draw() {
        let g = TicTacToe;
        let mut r = Rng::new(0);
        let s = g.initial(&mut r, 0);
        let mut solver = Solver::new();
        // Perfect play from the empty board is a draw → value 0.
        assert_eq!(solver.value(&g, &s), 0.0);
    }

    #[test]
    fn solver_says_nim_start_is_a_win() {
        let g = Nim;
        let mut r = Rng::new(0);
        let s = g.initial(&mut r, 0);
        let mut solver = Solver::new();
        // [3,4,5] has non-zero nim-sum → the player to move wins (+1).
        assert_eq!(solver.value(&g, &s), 1.0);
    }

    #[test]
    fn qlearner_converges_toward_optimal() {
        let g = TicTacToe;
        let mut q = QLearner::new(&g, 7);
        let start_mae = q.latest().mae;
        q.train(&g, 4000);
        let end = q.latest();
        assert!(
            end.mae < start_mae * 0.25,
            "MAE should shrink markedly: {} -> {}",
            start_mae,
            end.mae
        );
        // Learned value of the empty board should be near a draw.
        assert!(end.root_value.abs() < 0.2, "root value {}", end.root_value);
        // A converged tic-tac-toe policy should essentially never lose.
        assert!(end.eval_loss < 0.05, "eval loss too high: {}", end.eval_loss);
    }
}
