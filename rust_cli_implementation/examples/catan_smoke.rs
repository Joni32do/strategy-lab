//! Manual end-to-end smoke test of the Catan bridge: drives the real
//! `CatanLab` (the same code the TUI uses) against a running catanatron
//! server. Start the server first, then:  cargo run --example catan_smoke

use high_level::catan::CatanLab;

fn main() {
    let mut lab = CatanLab::new();

    lab.sync_defaults();
    println!("sync    : {}", lab.status);
    assert!(lab.server_seen, "server should be reachable on 127.0.0.1:8000");
    println!("opponents: {:?}", lab.opponents);

    lab.sim_n = 6;
    lab.simulate();
    println!("simulate: {}", lab.status);
    let r = lab.last_sim.as_ref().expect("a sim result");
    assert_eq!(r.you_wins + r.opp_wins + r.draws, r.games);
    println!(
        "  -> {} games, you {} / opp {} ({:.0}% winrate)",
        r.games, r.you_wins, r.opp_wins, r.winrate * 100.0
    );

    lab.new_game();
    println!("new game: {}", lab.status);
    let g = lab.game.as_ref().expect("a step game");
    assert!(!g.state.tiles.is_empty(), "board has tiles");
    assert_eq!(g.state.players.len(), 2, "two seats");

    for _ in 0..12 {
        lab.tick();
    }
    let g = lab.game.as_ref().unwrap();
    println!(
        "after 12 ticks: turn {}, last: {:?}",
        g.state.num_turns, g.last_action
    );
    assert!(g.log.len() > 1, "the log grew as we ticked");

    println!("\nOK: Rust client <-> catanatron bridge round-trip works.");
}
