//! `high-level selftest` — a headless run that proves the whole thing works
//! without a terminal: it folds the state space, simulates a match, trains the
//! value function, and renders every view into an in-memory buffer.

use std::io;

use crossterm::event::KeyCode;
use ratatui::{backend::TestBackend, buffer::Buffer, Terminal};

use crate::app::{App, GameId, Tab};
use crate::engine::{compute_stats, simulate_match};
use crate::game::{Nim, TicTacToe};
use crate::symmetry::analyze;
use crate::ui;

fn buffer_text(buf: &Buffer) -> String {
    let area = buf.area;
    let mut out = String::with_capacity((area.width as usize + 1) * area.height as usize);
    for y in 0..area.height {
        for x in 0..area.width {
            out.push_str(buf.get(area.x + x, area.y + y).symbol());
        }
        out.push('\n');
    }
    out
}

fn render(app: &App) -> String {
    let backend = TestBackend::new(140, 44);
    let mut term = Terminal::new(backend).expect("test terminal");
    term.draw(|f| ui::draw(app, f)).expect("draw");
    buffer_text(term.backend().buffer())
}

fn check(label: &str, cond: bool) {
    let mark = if cond { "ok  " } else { "FAIL" };
    println!("  [{mark}] {label}");
    assert!(cond, "self-test failed: {label}");
}

pub fn run() -> io::Result<()> {
    println!("high-level — self test\n");

    // --- symmetry --------------------------------------------------------- //
    println!("symmetry (state-space folding):");
    let ttt_sym = analyze(&TicTacToe);
    println!(
        "  tic-tac-toe: {} reachable → {} distinct under D4  ({:.2}× smaller)",
        ttt_sym.reachable,
        ttt_sym.canonical,
        ttt_sym.reduction()
    );
    check("tic-tac-toe folds to the classic 765 states", ttt_sym.canonical == 765);
    check("reachable count is the classic 5478", ttt_sym.reachable == 5478);
    let nim_sym = analyze(&Nim);
    println!(
        "  nim 3-4-5:   {} reachable → {} distinct under S3 ({:.2}× smaller)",
        nim_sym.reachable,
        nim_sym.canonical,
        nim_sym.reduction()
    );
    check("nim genuinely folds under heap permutation", nim_sym.canonical < nim_sym.reachable);

    // --- strategy / match engine ----------------------------------------- //
    println!("\nstrategy (100-game matches):");
    let perfect = [
        "win", "block", "fork", "block-fork", "center", "opp-corner", "corner", "edge",
    ];
    let perfect_ids: Vec<String> = perfect.iter().map(|s| s.to_string()).collect();
    let pal = crate::game::tictactoe::cards();
    let pp = compute_stats(&simulate_match(&TicTacToe, &pal, &perfect_ids, &perfect_ids, 100, 1));
    println!("  perfect vs perfect: {}-{}-{} (w-d-l)", pp.you, pp.draws, pp.opp);
    check("perfect vs perfect draws all 100", pp.draws == 100);
    let pr = compute_stats(&simulate_match(&TicTacToe, &pal, &perfect_ids, &[], 200, 2));
    println!("  perfect vs random:  {} wins, {} losses over 200", pr.you, pr.opp);
    check("a perfect policy never loses", pr.opp == 0);

    // --- value-function RL ------------------------------------------------ //
    println!("\nvalue-function RL (tic-tac-toe self-play):");
    let mut app = App::new();
    let start = app.ttt.learner.latest();
    for _ in 0..24 {
        app.ttt.train_batch();
    }
    let end = app.ttt.learner.latest();
    println!(
        "  episodes {:>5} → {:>5} | MAE {:.3} → {:.3} | V(start) {:+.2} | loss vs random {:.1}%",
        start.episodes,
        end.episodes,
        start.mae,
        end.mae,
        end.root_value,
        end.eval_loss * 100.0
    );
    check("the learned value function approaches optimal", end.mae < 0.06);
    check("the learned start value is near a draw", end.root_value.abs() < 0.15);
    check("the learned policy essentially never loses", end.eval_loss < 0.02);

    // --- drive the app & render every view -------------------------------- //
    println!("\nUI (render every view headlessly):");
    // discover a card, build a stack, run a match
    app.on_key(KeyCode::Char('s')); // scout
    app.on_key(KeyCode::Char('s')); // scout again
    app.on_key(KeyCode::Char('b')); // cycle opponent
    app.on_key(KeyCode::Char('r')); // run match
    let strat = render(&app);
    check("strategy view renders the lab", strat.contains("Your strategy"));
    check("strategy view shows discovery progress", strat.contains("discovered"));

    app.on_key(KeyCode::Char('2')); // value view
    app.on_key(KeyCode::Char('t')); // one training step
    let valv = render(&app);
    check("value view renders the learner", valv.contains("Self-play learner"));
    check("value view shows convergence", valv.contains("Convergence"));

    app.on_key(KeyCode::Char('3')); // symmetry view
    let symv = render(&app);
    check("symmetry view shows core decisions", symv.contains("real decisions"));
    check("symmetry view shows reduction", symv.contains("reduction factor"));

    app.on_key(KeyCode::Char('g')); // switch to nim
    check("game switched to nim", matches!(app.active, GameId::Nim));
    let nimv = render(&app);
    check("nim renders under the symmetry view", nimv.contains("Orbit"));

    app.on_key(KeyCode::Char('1'));
    check("tab switched back to strategy", matches!(app.tab, Tab::Strategy));
    let _ = render(&app); // nim strategy view renders without panic

    app.on_key(KeyCode::Char('g')); // switch to catan
    check("game switched to catan", matches!(app.active, GameId::Catan));
    let catan_tuner = render(&app);
    check("catan tuner renders the policy", catan_tuner.contains("Your policy"));
    app.on_key(KeyCode::Char('2')); // play tab
    let catan_play = render(&app);
    check("catan play renders the live-game panel", catan_play.contains("Live game"));
    app.on_key(KeyCode::Char('3')); // about tab
    check("catan about renders the bridge note", render(&app).contains("bridge"));

    println!("\nall checks passed.");
    Ok(())
}
