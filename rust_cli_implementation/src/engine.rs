//! The match engine: turn a pair of card stacks into 100 games of statistics.
//! Game-agnostic and side-effect free, exactly like the original Strategy Lab.

use crate::cards::{Card, Rule};
use crate::game::{Game, Seat, YOU};
use crate::rng::{game_seed, Rng};

/// Read the stack top-to-bottom and choose a move (or `None` to pass).
pub fn choose_move<G: Game>(
    g: &G,
    s: &G::State,
    stack: &[&Card<G>],
    seat: Seat,
    rng: &mut Rng,
) -> Option<G::Move> {
    let mut cands = g.legal_moves(s);
    if cands.is_empty() {
        return None;
    }
    for card in stack {
        if cands.len() == 1 {
            break;
        }
        match &card.rule {
            Rule::Avoid(f) => {
                let kept: Vec<G::Move> =
                    cands.iter().filter(|m| !f(g, s, m, seat)).cloned().collect();
                if !kept.is_empty() {
                    cands = kept; // never veto everything
                }
            }
            Rule::Pick(f) => {
                if let Some(m) = f(g, s, &cands, seat, rng) {
                    return Some(m);
                }
            }
        }
    }
    if cands.len() == 1 {
        Some(cands.into_iter().next().unwrap())
    } else {
        Some(rng.choice(&cands).clone())
    }
}

/// One recorded step of a game, for the replay viewer.
pub struct Frame<G: Game> {
    pub state: G::State,
    pub caption: String,
    pub seat: Option<Seat>,
}

pub struct GameOutcome<G: Game> {
    pub winner: Option<Seat>,
    pub turns: u32,
    pub timeout: bool,
    pub first: Seat,
    pub frames: Option<Vec<Frame<G>>>,
}

/// Play a single game to its end. `stacks[seat]` is that seat's policy.
pub fn play_game<G: Game>(
    g: &G,
    stacks: [&[&Card<G>]; 2],
    first: Seat,
    seed: u32,
    record: bool,
) -> GameOutcome<G> {
    let mut rng = Rng::new(seed);
    let mut state = g.initial(&mut rng, first);
    let mut frames = record.then(|| {
        vec![Frame {
            state: state.clone(),
            caption: "Game start".into(),
            seat: None,
        }]
    });
    let max_turns = g.max_turns();
    let mut turns = 0u32;

    while !g.is_terminal(&state) && turns < max_turns {
        let seat = g.current(&state);
        let mv = choose_move(g, &state, stacks[seat], seat, &mut rng);
        let caption = if record {
            g.describe(&state, mv.as_ref(), seat)
        } else {
            String::new()
        };
        state = g.apply(&state, mv.as_ref(), &mut rng);
        if let Some(fr) = frames.as_mut() {
            fr.push(Frame { state: state.clone(), caption, seat: Some(seat) });
        }
        turns += 1;
    }

    let (winner, timeout) = if g.is_terminal(&state) {
        (g.winner(&state), false)
    } else {
        (g.timeout_winner(&state), true)
    };
    GameOutcome { winner, turns, timeout, first, frames }
}

#[derive(Clone, Copy)]
pub struct GameResult {
    pub winner: Option<Seat>,
    pub turns: u32,
    pub timeout: bool,
    pub first: Seat,
}

/// A match = `n` games, alternating who starts, each with its own seed.
pub fn simulate_match<G: Game>(
    g: &G,
    palette: &[Card<G>],
    you_ids: &[String],
    opp_ids: &[String],
    n: usize,
    base_seed: u32,
) -> Vec<GameResult> {
    let you_refs: Vec<&str> = you_ids.iter().map(|s| s.as_str()).collect();
    let opp_refs: Vec<&str> = opp_ids.iter().map(|s| s.as_str()).collect();
    let you_stack = crate::cards::resolve(palette, &you_refs);
    let opp_stack = crate::cards::resolve(palette, &opp_refs);
    let stacks: [&[&Card<G>]; 2] = [&you_stack, &opp_stack];

    (0..n)
        .map(|i| {
            let o = play_game(g, stacks, i % 2, game_seed(base_seed, i), false);
            GameResult { winner: o.winner, turns: o.turns, timeout: o.timeout, first: o.first }
        })
        .collect()
}

/// Re-play one specific game of a match with full frame recording.
pub fn replay_game<G: Game>(
    g: &G,
    palette: &[Card<G>],
    you_ids: &[String],
    opp_ids: &[String],
    index: usize,
    base_seed: u32,
) -> GameOutcome<G> {
    let you_refs: Vec<&str> = you_ids.iter().map(|s| s.as_str()).collect();
    let opp_refs: Vec<&str> = opp_ids.iter().map(|s| s.as_str()).collect();
    let you_stack = crate::cards::resolve(palette, &you_refs);
    let opp_stack = crate::cards::resolve(palette, &opp_refs);
    play_game(g, [&you_stack, &opp_stack], index % 2, game_seed(base_seed, index), true)
}

/// Aggregate statistics over a match, mirroring the original results screen.
#[derive(Clone)]
pub struct MatchStats {
    pub n: usize,
    pub you: usize,
    pub opp: usize,
    pub draws: usize,
    pub avg_turns: f64,
    pub max_streak_you: usize,
    pub max_streak_opp: usize,
    pub you_start_wins: usize,
    pub you_start_games: usize,
    pub you_second_wins: usize,
    pub you_second_games: usize,
    /// Cumulative lead (you wins − opp wins) after each game; starts at 0.
    pub momentum: Vec<i32>,
    pub first_you_win: Option<usize>,
    pub first_opp_win: Option<usize>,
    pub first_draw: Option<usize>,
    pub longest_game: Option<usize>,
}

pub fn compute_stats(results: &[GameResult]) -> MatchStats {
    let n = results.len();
    let (mut you, mut opp, mut draws) = (0, 0, 0);
    let mut turns_sum = 0u64;
    let (mut cur_you, mut cur_opp, mut max_you, mut max_opp) = (0, 0, 0, 0);
    let (mut you_start_wins, mut you_start_games) = (0, 0);
    let (mut you_second_wins, mut you_second_games) = (0, 0);
    let mut momentum = vec![0i32];
    let mut lead = 0i32;
    let mut first_you_win = None;
    let mut first_opp_win = None;
    let mut first_draw = None;
    let mut longest_game = None;
    let mut longest_turns = 0u32;

    for (i, r) in results.iter().enumerate() {
        turns_sum += r.turns as u64;
        if r.turns > longest_turns {
            longest_turns = r.turns;
            longest_game = Some(i);
        }
        if r.first == YOU {
            you_start_games += 1;
        } else {
            you_second_games += 1;
        }
        match r.winner {
            Some(YOU) => {
                you += 1;
                first_you_win.get_or_insert(i);
                cur_you += 1;
                cur_opp = 0;
                lead += 1;
                if r.first == YOU {
                    you_start_wins += 1;
                } else {
                    you_second_wins += 1;
                }
            }
            Some(_) => {
                opp += 1;
                first_opp_win.get_or_insert(i);
                cur_opp += 1;
                cur_you = 0;
                lead -= 1;
            }
            None => {
                draws += 1;
                first_draw.get_or_insert(i);
                cur_you = 0;
                cur_opp = 0;
            }
        }
        max_you = max_you.max(cur_you);
        max_opp = max_opp.max(cur_opp);
        momentum.push(lead);
    }

    MatchStats {
        n,
        you,
        opp,
        draws,
        avg_turns: if n > 0 { turns_sum as f64 / n as f64 } else { 0.0 },
        max_streak_you: max_you,
        max_streak_opp: max_opp,
        you_start_wins,
        you_start_games,
        you_second_wins,
        you_second_games,
        momentum,
        first_you_win,
        first_opp_win,
        first_draw,
        longest_game,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::{nim, tictactoe, Nim, TicTacToe};

    fn ids(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn perfect_vs_perfect_is_all_draws() {
        let g = TicTacToe;
        let palette = tictactoe::cards();
        let perfect = ids(&[
            "win", "block", "fork", "block-fork", "center", "opp-corner", "corner", "edge",
        ]);
        let results = simulate_match(&g, &palette, &perfect, &perfect, 100, 12345);
        let st = compute_stats(&results);
        assert_eq!(st.draws, 100, "perfect play must draw every game");
    }

    #[test]
    fn perfect_never_loses_to_random() {
        let g = TicTacToe;
        let palette = tictactoe::cards();
        let perfect = ids(&[
            "win", "block", "fork", "block-fork", "center", "opp-corner", "corner", "edge",
        ]);
        let random = ids(&[]);
        let results = simulate_match(&g, &palette, &perfect, &random, 200, 999);
        let st = compute_stats(&results);
        assert_eq!(st.opp, 0, "a perfect policy can never lose");
        assert!(st.you > 0, "and should beat a random opponent sometimes");
    }

    #[test]
    fn momentum_has_n_plus_one_points() {
        let g = TicTacToe;
        let palette = tictactoe::cards();
        let results = simulate_match(&g, &palette, &ids(&["win"]), &ids(&[]), 30, 1);
        let st = compute_stats(&results);
        assert_eq!(st.momentum.len(), 31);
    }

    #[test]
    fn nim_perfect_dominates_random() {
        let g = Nim;
        let palette = nim::cards();
        let perfect = ids(&["xor", "balanced", "big"]);
        let results = simulate_match(&g, &palette, &perfect, &ids(&[]), 200, 5);
        let st = compute_stats(&results);
        // Always wins when moving first (non-zero start); usually punishes a
        // random first mover too. A large majority is expected.
        assert!(st.you > 150, "nim perfect should crush random: {} vs {}", st.you, st.opp);
    }

    #[test]
    fn avoid_only_stack_never_deadlocks() {
        // The 'balanced' AVOID card alone must still always produce a move
        // (the engine never vetoes every candidate).
        let g = Nim;
        let palette = nim::cards();
        let results = simulate_match(&g, &palette, &ids(&["balanced"]), &ids(&[]), 50, 9);
        let st = compute_stats(&results);
        assert_eq!(st.you + st.opp + st.draws, 50);
        assert!(results.iter().all(|r| !r.timeout), "no game stalled");
    }
}
