//! The Catan lens — terminal rendering for the catanatron bridge.
//!
//! Unlike Tic-Tac-Toe and Nim, Catan is not a `Game` here (too big to solve),
//! so it has no `Session` and none of the three solver-driven lenses. Instead
//! the three tabs become three ways of *working with a policy* against the real
//! engine:
//!
//!   1 Tuner   — design the position-strength weights and the trade coefficient,
//!               then simulate a batch of games and read the win bars.
//!   2 Play    — step a single live game ply-by-ply and watch the policy reason.
//!   3 About   — what this lens is, and how to bring the engine up.
//!
//! Everything here is read-only over [`CatanLab`]; all state changes happen in
//! `app.rs` (`on_catan_key`).

use ratatui::{prelude::*, widgets::*};

use super::*;
use crate::app::Tab;
use crate::catan::{lambda_curve, CatanLab, Param, PlayerInfo, StepGame};

/// Colours for the four catanatron seats, plus a fallback.
fn color_for(name: &str) -> Color {
    match name.to_ascii_uppercase().as_str() {
        "RED" => Color::Rgb(255, 92, 124),
        "BLUE" => Color::Rgb(95, 212, 245),
        "ORANGE" => Color::Rgb(255, 169, 77),
        "WHITE" => Color::Rgb(232, 234, 246),
        "GREEN" => GOOD,
        _ => MUTED,
    }
}

/// A short glyph for a resource / tile, single terminal cell wide.
fn resource_glyph(res: Option<&str>) -> (&'static str, Color) {
    match res.map(|r| r.to_ascii_lowercase()) {
        Some(ref r) if r == "wood" => ("W", GOOD),
        Some(ref r) if r == "brick" => ("B", Color::Rgb(210, 120, 80)),
        Some(ref r) if r == "sheep" => ("S", Color::Rgb(150, 220, 150)),
        Some(ref r) if r == "wheat" => ("H", GOLD),
        Some(ref r) if r == "ore" => ("O", Color::Rgb(160, 170, 200)),
        Some(ref r) if r == "desert" => ("·", MUTED),
        _ => (" ", MUTED),
    }
}

pub fn render(lab: &CatanLab, tab: Tab, f: &mut Frame, area: Rect) {
    match tab {
        Tab::Strategy => tuner(lab, f, area),
        Tab::Value => play(lab, f, area),
        Tab::Symmetry => about(lab, f, area),
    }
}

// --------------------------------------------------------------------------- //
// Tab 1 — Tuner & Simulate
// --------------------------------------------------------------------------- //
fn tuner(lab: &CatanLab, f: &mut Frame, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);

    params_panel(lab, f, cols[0]);

    let right = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(8), Constraint::Length(11)])
        .split(cols[1]);
    simulate_panel(lab, f, right[0]);
    lambda_panel(lab, f, right[1]);
}

fn params_panel(lab: &CatanLab, f: &mut Frame, area: Rect) {
    let blk = panel("Your policy — you design it");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let bar_w = (inner.width as usize).saturating_sub(26).clamp(6, 20);
    let mut lines: Vec<Line> = Vec::new();

    lines.push(section("Position strength (share of value)"));
    for (i, p) in lab.weights.iter().enumerate() {
        lines.push(param_line(p, i == lab.cursor, bar_w));
    }
    lines.push(Line::from(""));
    lines.push(section("Trade policy (the non-linear coefficient λ)"));
    for (j, p) in lab.trade.iter().enumerate() {
        let idx = lab.weights.len() + j;
        lines.push(param_line(p, idx == lab.cursor, bar_w));
    }
    lines.push(Line::from(""));
    // The help text for whichever param the cursor is on.
    let cur = lab.param_at(lab.cursor);
    lines.push(Line::from(vec![
        Span::styled(format!("{}: ", cur.label), Style::default().fg(GOLD)),
        Span::styled(cur.help.to_string(), Style::default().fg(MUTED)),
    ]));

    // trim:false so the two-space marker column stays aligned across rows.
    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: false }), inner);
}

fn param_line(p: &Param, selected: bool, bar_w: usize) -> Line<'static> {
    let filled = (p.frac() * bar_w as f64).round() as usize;
    let filled = filled.min(bar_w);
    let bar: String = format!("{}{}", "█".repeat(filled), "░".repeat(bar_w - filled));
    let marker = if selected {
        Span::styled("▸ ", Style::default().fg(YOU_C).add_modifier(Modifier::BOLD))
    } else {
        Span::raw("  ")
    };
    let label_style = if selected {
        Style::default().fg(TEXT).add_modifier(Modifier::BOLD)
    } else {
        Style::default().fg(MUTED)
    };
    Line::from(vec![
        marker,
        Span::styled(format!("{:<14}", p.label), label_style),
        Span::styled(bar, Style::default().fg(if selected { YOU_C } else { PICK_C })),
        Span::styled(format!(" {:>6}", p.display()), Style::default().fg(TEXT)),
    ])
}

fn simulate_panel(lab: &CatanLab, f: &mut Frame, area: Rect) {
    let blk = panel("Simulate a batch");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let trade = if lab.enable_trade { "on" } else { "off" };
    let mut lines = vec![
        Line::from(vec![
            Span::styled("opponent ", Style::default().fg(MUTED)),
            Span::styled(
                format!("{:<10}", lab.opponent_name()),
                Style::default().fg(OPP_C).add_modifier(Modifier::BOLD),
            ),
            Span::styled(" [o/O]", Style::default().fg(MUTED)),
        ]),
        Line::from(vec![
            Span::styled("games    ", Style::default().fg(MUTED)),
            Span::styled(format!("{:<10}", lab.sim_n), Style::default().fg(TEXT)),
            Span::styled(" [ / ]", Style::default().fg(MUTED)),
        ]),
        Line::from(vec![
            Span::styled("trades   ", Style::default().fg(MUTED)),
            Span::styled(format!("{:<10}", trade), Style::default().fg(TEXT)),
            Span::styled(" [T]", Style::default().fg(MUTED)),
        ]),
        Line::from(""),
    ];

    if let Some(r) = lab.last_sim.as_ref() {
        let w = (inner.width as usize).saturating_sub(2).clamp(6, 40);
        lines.push(outcome_bar(r.you_wins, r.draws, r.opp_wins, w));
        lines.push(Line::from(vec![
            Span::styled(
                format!("you {} ", r.you_wins),
                Style::default().fg(YOU_C).add_modifier(Modifier::BOLD),
            ),
            Span::styled(format!("· {} draws · ", r.draws), Style::default().fg(MUTED)),
            Span::styled(
                format!("{} {}", r.opponent, r.opp_wins),
                Style::default().fg(OPP_C),
            ),
            Span::styled(
                format!("   winrate {:.0}%", r.winrate * 100.0),
                Style::default().fg(value_color(r.winrate * 2.0 - 1.0)).add_modifier(Modifier::BOLD),
            ),
        ]));
        lines.push(Line::from(vec![
            Span::styled("avg VP ", Style::default().fg(MUTED)),
            Span::styled(format!("{:.1}", r.avg_your_vp), Style::default().fg(YOU_C)),
            Span::styled(" vs ", Style::default().fg(MUTED)),
            Span::styled(format!("{:.1}", r.avg_opp_vp), Style::default().fg(OPP_C)),
            Span::styled(
                format!("   avg length {:.0} turns", r.avg_turns),
                Style::default().fg(MUTED),
            ),
        ]));
        let total_trades = r.offers;
        if total_trades > 0 {
            lines.push(Line::from(vec![
                Span::styled("trades  ", Style::default().fg(MUTED)),
                Span::styled(
                    format!(
                        "{} offered · {} accepted · {} vetoed",
                        r.offers, r.accepts, r.vetoes
                    ),
                    Style::default().fg(TEXT),
                ),
            ]));
        }
    } else {
        lines.push(Line::from(Span::styled(
            "No run yet. Press [r] to simulate against the engine.",
            Style::default().fg(MUTED),
        )));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        status_glyph(lab),
        Style::default().fg(if lab.server_seen { GOOD } else { GOLD }),
    )));
    lines.push(Line::from(Span::styled(
        truncate(&lab.status, inner.width as usize * 2),
        Style::default().fg(MUTED),
    )));

    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}

fn lambda_panel(lab: &CatanLab, f: &mut Frame, area: Rect) {
    // Sample the logistic trade coefficient across opponent strength [0, 1].
    let pts: Vec<(f64, f64)> = (0..=40)
        .map(|i| {
            let x = i as f64 / 40.0;
            (x, lambda_curve(&lab.trade, x))
        })
        .collect();
    let ymax = pts.iter().map(|p| p.1).fold(0.1, f64::max).max(0.1);
    let datasets = vec![Dataset::default()
        .name("λ(opp strength)")
        .marker(symbols::Marker::Braille)
        .graph_type(GraphType::Line)
        .style(Style::default().fg(PICK_C))
        .data(&pts)];
    let chart = Chart::new(datasets)
        .block(panel("Trade coefficient λ vs opponent strength"))
        .x_axis(
            Axis::default()
                .style(Style::default().fg(MUTED))
                .bounds([0.0, 1.0])
                .labels(vec![
                    Span::styled("weak", Style::default().fg(MUTED)),
                    Span::styled("strong", Style::default().fg(MUTED)),
                ]),
        )
        .y_axis(
            Axis::default()
                .style(Style::default().fg(MUTED))
                .bounds([0.0, ymax])
                .labels(vec![
                    Span::styled("0", Style::default().fg(MUTED)),
                    Span::styled(format!("{ymax:.1}"), Style::default().fg(MUTED)),
                ]),
        );
    f.render_widget(chart, area);
}

// --------------------------------------------------------------------------- //
// Tab 2 — Step-through play
// --------------------------------------------------------------------------- //
fn play(lab: &CatanLab, f: &mut Frame, area: Rect) {
    let Some(game) = lab.game.as_ref() else {
        let blk = panel("Live game");
        let inner = blk.inner(area);
        f.render_widget(blk, area);
        let lines = vec![
            Line::from(""),
            Line::from(Span::styled(
                "  No game running.",
                Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
            )),
            Line::from(""),
            Line::from(Span::styled(
                "  Press [n] to deal a fresh board against the current opponent,",
                Style::default().fg(MUTED),
            )),
            Line::from(Span::styled(
                "  then [t] to tick one ply or [f] to fast-forward ten.",
                Style::default().fg(MUTED),
            )),
            Line::from(""),
            Line::from(Span::styled(status_glyph(lab), Style::default().fg(if lab.server_seen { GOOD } else { GOLD }))),
            Line::from(Span::styled(format!("  {}", lab.status), Style::default().fg(MUTED))),
        ];
        f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
        return;
    };

    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(46), Constraint::Percentage(54)])
        .split(area);

    board_panel(game, f, cols[0]);

    let right = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(8), Constraint::Length(4), Constraint::Min(4)])
        .split(cols[1]);
    players_panel(game, f, right[0]);
    action_panel(game, f, right[1]);
    log_panel(game, f, right[2]);
}

fn board_panel(game: &StepGame, f: &mut Frame, area: Rect) {
    let title = format!("Board — seed {} · turn {}", game.seed, game.state.num_turns);
    let blk = panel(&title);
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let tiles = &game.state.tiles;
    // The classic base board is 19 tiles laid out 3-4-5-4-3; anything else we
    // wrap into a plain grid so novel maps still render.
    let rows_layout: Vec<usize> = if tiles.len() == 19 {
        vec![3, 4, 5, 4, 3]
    } else {
        let per = ((tiles.len() as f64).sqrt().ceil() as usize).max(1);
        let mut v = vec![per; tiles.len() / per];
        if tiles.len() % per != 0 {
            v.push(tiles.len() % per);
        }
        v
    };

    let mut lines: Vec<Line> = vec![Line::from("")];
    let mut idx = 0usize;
    let widest = rows_layout.iter().copied().max().unwrap_or(1);
    for &count in &rows_layout {
        let pad = (widest - count) * 3;
        let mut spans: Vec<Span> = vec![Span::raw(" ".repeat(pad + 1))];
        for _ in 0..count {
            if idx >= tiles.len() {
                break;
            }
            let t = &tiles[idx];
            let (glyph, col) = resource_glyph(t.resource.as_deref());
            let robber = game.state.robber_tile == Some(idx);
            let num = t.number.map(|n| format!("{n:>2}")).unwrap_or_else(|| "  ".into());
            let cell_style = if robber {
                Style::default().fg(BG).bg(col).add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(col).add_modifier(Modifier::BOLD)
            };
            spans.push(Span::styled(format!("{glyph}{num} "), cell_style));
            idx += 1;
        }
        lines.push(Line::from(spans));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(vec![
        Span::styled("  buildings ", Style::default().fg(MUTED)),
        Span::styled(format!("{}", game.state.num_buildings), Style::default().fg(TEXT)),
        Span::styled("  roads ", Style::default().fg(MUTED)),
        Span::styled(format!("{}", game.state.num_roads), Style::default().fg(TEXT)),
    ]));
    lines.push(Line::from(Span::styled(
        "  W wood  B brick  S sheep  H wheat  O ore",
        Style::default().fg(MUTED),
    )));
    lines.push(Line::from(Span::styled(
        "  reverse video = robber",
        Style::default().fg(MUTED),
    )));

    f.render_widget(Paragraph::new(lines), inner);
}

fn players_panel(game: &StepGame, f: &mut Frame, area: Rect) {
    let blk = panel("Players");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let mut lines: Vec<Line> = Vec::new();
    for p in &game.state.players {
        lines.push(player_line(p, &game.state.current_color));
    }
    if let Some(w) = game.state.winner.as_ref() {
        lines.push(Line::from(Span::styled(
            format!("  ▶ {w} wins the game"),
            Style::default().fg(GOLD).add_modifier(Modifier::BOLD),
        )));
    }
    f.render_widget(Paragraph::new(lines), inner);
}

fn player_line(p: &PlayerInfo, current: &str) -> Line<'static> {
    let col = color_for(&p.color);
    let marker = if p.color.eq_ignore_ascii_case(current) { "▸" } else { " " };
    let you = if p.is_you { " (you)" } else { "" };
    let hand: u64 = p.hand.iter().sum();
    Line::from(vec![
        Span::styled(format!("{marker} "), Style::default().fg(GOLD)),
        Span::styled(
            format!("{:<7}", format!("{}{}", short_color(&p.color), you)),
            Style::default().fg(col).add_modifier(Modifier::BOLD),
        ),
        Span::styled(format!("{} VP  ", p.vp), Style::default().fg(TEXT)),
        Span::styled(format!("hand {hand}  "), Style::default().fg(MUTED)),
        Span::styled(format!("dev {}  ", p.dev_cards), Style::default().fg(MUTED)),
        Span::styled(format!("road {}  ", p.longest_road), Style::default().fg(MUTED)),
        Span::styled(format!("str {:.2}", p.strength), Style::default().fg(value_color(p.strength * 2.0 - 1.0))),
    ])
}

fn short_color(c: &str) -> String {
    let c = c.to_ascii_uppercase();
    if c.len() > 6 {
        c[..6].to_string()
    } else {
        c
    }
}

fn action_panel(game: &StepGame, f: &mut Frame, area: Rect) {
    let blk = panel("Last move");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let action = game.last_action.clone().unwrap_or_else(|| "— press [t] to tick —".into());
    let expl = game.last_explanation.clone().unwrap_or_default();
    let lines = vec![
        Line::from(Span::styled(action, Style::default().fg(TEXT).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled(expl, Style::default().fg(PICK_C))),
    ];
    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}

fn log_panel(game: &StepGame, f: &mut Frame, area: Rect) {
    let blk = panel("Log");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let h = inner.height as usize;
    let start = game.log.len().saturating_sub(h);
    let lines: Vec<Line> = game.log[start..]
        .iter()
        .map(|l| Line::from(Span::styled(l.clone(), Style::default().fg(MUTED))))
        .collect();
    f.render_widget(Paragraph::new(lines), inner);
}

// --------------------------------------------------------------------------- //
// Tab 3 — About
// --------------------------------------------------------------------------- //
fn about(lab: &CatanLab, f: &mut Frame, area: Rect) {
    let blk = panel("The Catan lens — a bridge, not a solve");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let p = |s: &str| Line::from(Span::styled(s.to_string(), Style::default().fg(TEXT)));
    let m = |s: &str| Line::from(Span::styled(s.to_string(), Style::default().fg(MUTED)));
    let lines = vec![
        p("Tic-Tac-Toe and Nim are small enough to solve exactly, so we can look"),
        p("at them through three lenses. Settlers of Catan is not: dice, four"),
        p("seats, an enormous state space. So this view flips the idea around."),
        Line::from(""),
        p("The real catanatron engine computes every rule, roll and move behind a"),
        p("small HTTP API. You do not play the moves — you design the policy:"),
        Line::from(""),
        Line::from(vec![
            Span::styled("  · position strength  ", Style::default().fg(PICK_C)),
            Span::styled("a weighted blend of VP, production and reach", Style::default().fg(MUTED)),
        ]),
        Line::from(vec![
            Span::styled("  · trade coefficient  ", Style::default().fg(PICK_C)),
            Span::styled("a logistic λ that hardens as the opponent leads", Style::default().fg(MUTED)),
        ]),
        Line::from(""),
        p("Tune it in tab 1, simulate a batch, then watch a single game reason"),
        p("its way through tab 2."),
        Line::from(""),
        Line::from(Span::styled(status_glyph(lab), Style::default().fg(if lab.server_seen { GOOD } else { GOLD }))),
        m(&format!("Engine endpoint: {}", lab.client.base())),
        m("Start it from the repo root:  ./scripts/catan-server.sh"),
        m("(or:  cd catan-server && python3 -m venv .venv && .venv/bin/pip install -e ../catanatron && .venv/bin/python app.py)"),
        Line::from(""),
        m(&lab.status),
    ];
    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //
fn section(title: &str) -> Line<'static> {
    Line::from(Span::styled(
        format!(" {title}"),
        Style::default().fg(PICK_C).add_modifier(Modifier::BOLD),
    ))
}

fn status_glyph(lab: &CatanLab) -> String {
    if lab.server_seen {
        format!("● connected to catanatron at {}", lab.client.base())
    } else {
        format!("○ engine not reached at {} — press [d] to retry", lab.client.base())
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        s.chars().take(max.saturating_sub(1)).collect::<String>() + "…"
    }
}
