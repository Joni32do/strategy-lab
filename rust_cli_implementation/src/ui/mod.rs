//! Terminal rendering (ratatui). Three views, one chrome, two overlays.
//! Everything here is read-only over `App`/`Session` — all state changes happen
//! in `app.rs`.

mod catan;
mod strategy;
mod symmetry;
mod value;

use ratatui::{prelude::*, widgets::*};

use crate::app::{App, GameId, Tab};
use crate::game::{BoardSketch, Game, Seat, YOU};

// ---- theme ----------------------------------------------------------------- //
pub const BG: Color = Color::Rgb(12, 14, 26);
pub const PANEL: Color = Color::Rgb(27, 32, 54);
pub const BORDER: Color = Color::Rgb(39, 45, 73);
pub const BORDER_HI: Color = Color::Rgb(90, 100, 150);
pub const TEXT: Color = Color::Rgb(232, 234, 246);
pub const MUTED: Color = Color::Rgb(139, 145, 181);
pub const YOU_C: Color = Color::Rgb(255, 169, 77);
pub const OPP_C: Color = Color::Rgb(95, 212, 245);
pub const PICK_C: Color = Color::Rgb(155, 123, 255);
pub const AVOID_C: Color = Color::Rgb(255, 92, 124);
pub const GOOD: Color = Color::Rgb(81, 207, 102);
pub const BAD: Color = Color::Rgb(255, 92, 124);
pub const GOLD: Color = Color::Rgb(255, 209, 102);

pub fn seat_color(seat: Seat) -> Color {
    if seat == YOU {
        YOU_C
    } else {
        OPP_C
    }
}

/// Red→grey→green tint for a value in [-1, 1].
pub fn value_color(v: f64) -> Color {
    let v = v.clamp(-1.0, 1.0);
    if v >= 0.0 {
        let t = v;
        lerp(Color::Rgb(150, 150, 160), GOOD, t)
    } else {
        lerp(Color::Rgb(150, 150, 160), BAD, -v)
    }
}
fn lerp(a: Color, b: Color, t: f64) -> Color {
    let (Color::Rgb(ar, ag, ab), Color::Rgb(br, bg, bb)) = (a, b) else {
        return a;
    };
    let m = |x: u8, y: u8| (x as f64 + (y as f64 - x as f64) * t).round() as u8;
    Color::Rgb(m(ar, br), m(ag, bg), m(ab, bb))
}

pub fn panel(title: &str) -> Block<'_> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER))
        .title(Span::styled(
            format!(" {title} "),
            Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
        ))
        .style(Style::default().bg(PANEL))
}

pub fn panel_focused(title: &str, focused: bool) -> Block<'_> {
    let b = panel(title);
    if focused {
        b.border_style(Style::default().fg(GOLD).add_modifier(Modifier::BOLD))
    } else {
        b
    }
}

pub fn stars(n: u8) -> String {
    let n = n.min(4) as usize;
    format!("{}{}", "★".repeat(n), "☆".repeat(4 - n))
}

// ---- top-level ------------------------------------------------------------- //
pub fn draw(app: &App, f: &mut Frame) {
    let area = f.size();
    f.render_widget(Block::default().style(Style::default().bg(BG)), area);

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(0), Constraint::Length(1)])
        .split(area);

    header(app, f, rows[0]);
    match app.active {
        GameId::Ttt => view(app, &app.ttt, f, rows[1]),
        GameId::Nim => view(app, &app.nim, f, rows[1]),
        GameId::Catan => catan::render(&app.catan, app.tab, f, rows[1]),
    }
    status(app, f, rows[2]);

    if app.replay.is_some() {
        replay_overlay(app, f, area);
    }
    if app.show_help {
        help_overlay(f, area);
    }
}

fn view<G: Game>(app: &App, s: &crate::app::Session<G>, f: &mut Frame, area: Rect) {
    match app.tab {
        Tab::Strategy => strategy::render(s, f, area),
        Tab::Value => value::render(s, f, area),
        Tab::Symmetry => symmetry::render(s, f, area),
    }
}

fn header(app: &App, f: &mut Frame, area: Rect) {
    let blk = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(BORDER))
        .style(Style::default().bg(PANEL));
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let tab_span = |label: &str, on: bool| {
        if on {
            Span::styled(
                format!(" {label} "),
                Style::default().fg(BG).bg(GOLD).add_modifier(Modifier::BOLD),
            )
        } else {
            Span::styled(format!(" {label} "), Style::default().fg(MUTED))
        }
    };
    // Catan is a bridge, not a solved game, so it renames the three tabs and
    // tagline; the two real `Game`s keep the "three lenses" framing.
    let (gname, gicon, tagline, labels) = match app.active {
        GameId::Ttt => (
            crate::game::TicTacToe::NAME,
            crate::game::TicTacToe::ICON,
            "three lenses on a solved game",
            ["1 Strategy", "2 Value-RL", "3 Symmetry"],
        ),
        GameId::Nim => (
            crate::game::Nim::NAME,
            crate::game::Nim::ICON,
            "three lenses on a solved game",
            ["1 Strategy", "2 Value-RL", "3 Symmetry"],
        ),
        GameId::Catan => (
            "Catan",
            "⬡",
            "design the policy, let the engine play",
            ["1 Tuner", "2 Play", "3 About"],
        ),
    };

    let line = Line::from(vec![
        Span::styled("high-level", Style::default().fg(YOU_C).add_modifier(Modifier::BOLD)),
        Span::styled(format!("  ·  {tagline}   "), Style::default().fg(MUTED)),
        tab_span(labels[0], matches!(app.tab, Tab::Strategy)),
        Span::raw(" "),
        tab_span(labels[1], matches!(app.tab, Tab::Value)),
        Span::raw(" "),
        tab_span(labels[2], matches!(app.tab, Tab::Symmetry)),
        Span::styled("    game: ", Style::default().fg(MUTED)),
        Span::styled(
            format!("{gicon} {gname}"),
            Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
        ),
        Span::styled("  [g switch]", Style::default().fg(MUTED)),
    ]);
    f.render_widget(Paragraph::new(line), inner);
}

fn status(app: &App, f: &mut Frame, area: Rect) {
    let hint = if app.show_help {
        "esc close help"
    } else if app.replay.is_some() {
        "← → step · home/end · esc close"
    } else if app.active == GameId::Catan {
        match app.tab {
            Tab::Strategy => "↑↓ param · ←→ adjust · o opponent · T trades · [ ] games · r simulate · R reset · d sync",
            Tab::Value => "n new game · t tick · f fast-forward 10 · o opponent · d sync",
            Tab::Symmetry => "d sync with engine · g switch game",
        }
    } else {
        match app.tab {
            Tab::Strategy => "tab focus · ↑↓ move · ⏎ add/remove · [ ] reorder · s scout · b bot · r run · v replay",
            Tab::Value => "space auto-train · t step · R reset · ↑↓ pick move · ⏎ play · u undo · n new",
            Tab::Symmetry => "↑↓ pick move · ⏎ play · u undo · n new board",
        }
    };
    let line = Line::from(vec![
        Span::styled(" ? help ", Style::default().fg(BG).bg(MUTED)),
        Span::raw("  "),
        Span::styled(hint, Style::default().fg(MUTED)),
        Span::styled("   ·  q quit", Style::default().fg(MUTED)),
    ]);
    f.render_widget(Paragraph::new(line).style(Style::default().bg(BG)), area);
}

// ---- board sketch renderer ------------------------------------------------- //
pub struct BoardOpts {
    pub selected_cell: Option<usize>,
    /// Per-cell value to show on empty cells (len == #cells), `None` to skip.
    pub cell_values: Vec<Option<f64>>,
    pub tint: bool,
}
impl BoardOpts {
    pub fn plain() -> Self {
        BoardOpts { selected_cell: None, cell_values: vec![], tint: false }
    }
}

/// Map a list of (move, value) onto grid cells for the heatmap overlay.
pub fn grid_cell_values<G: Game>(
    s: &crate::app::Session<G>,
    vals: &[(G::Move, f64)],
) -> Vec<Option<f64>> {
    let n = match s.sketch() {
        BoardSketch::Grid { cells, .. } => cells.len(),
        _ => return vec![],
    };
    let mut out = vec![None; n];
    for (mv, v) in vals {
        if let Some(c) = s.game.move_cell(&s.explore, mv) {
            if c < n {
                out[c] = Some(*v);
            }
        }
    }
    out
}

pub fn render_sketch(sketch: &BoardSketch, opts: &BoardOpts, f: &mut Frame, area: Rect) {
    match sketch {
        BoardSketch::Grid { cols, cells } => render_grid(*cols, cells, opts, f, area),
        BoardSketch::Heaps { labels, counts, max } => {
            render_heaps(labels, counts, *max, f, area)
        }
    }
}

fn render_grid(
    cols: usize,
    cells: &[crate::game::SketchCell],
    opts: &BoardOpts,
    f: &mut Frame,
    area: Rect,
) {
    let rows = (cells.len() + cols - 1) / cols;
    // square-ish cells; clamp to available area
    let cell_w = ((area.width as usize) / cols).min(7).max(3) as u16;
    let cell_h = ((area.height as usize) / rows).min(3).max(2) as u16;
    let grid_w = cell_w * cols as u16;
    let grid_h = cell_h * rows as u16;
    let ox = area.x + area.width.saturating_sub(grid_w) / 2;
    let oy = area.y + area.height.saturating_sub(grid_h) / 2;

    for (i, cell) in cells.iter().enumerate() {
        let r = (i / cols) as u16;
        let c = (i % cols) as u16;
        let rect = Rect {
            x: ox + c * cell_w,
            y: oy + r * cell_h,
            width: cell_w,
            height: cell_h,
        };
        if rect.x + rect.width > area.x + area.width || rect.y + rect.height > area.y + area.height {
            continue;
        }
        let selected = opts.selected_cell == Some(i);
        let mut border = Style::default().fg(BORDER);
        if cell.highlighted {
            border = Style::default().fg(GOLD).add_modifier(Modifier::BOLD);
        }
        if selected {
            border = Style::default().fg(YOU_C).add_modifier(Modifier::BOLD);
        }
        let mut bg = PANEL;
        let val = opts.cell_values.get(i).copied().flatten();
        if opts.tint {
            if let Some(v) = val {
                if cell.owner.is_none() {
                    bg = tint_bg(v);
                }
            }
        }
        let blk = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Plain)
            .border_style(border)
            .style(Style::default().bg(bg));
        let inner = blk.inner(rect);
        f.render_widget(blk, rect);

        let content: Line = if let Some(owner) = cell.owner {
            Line::from(Span::styled(
                cell.text.clone(),
                Style::default().fg(seat_color(owner)).add_modifier(Modifier::BOLD),
            ))
        } else if let Some(v) = val {
            Line::from(Span::styled(
                format!("{:+.0}", v * 100.0),
                Style::default().fg(value_color(v)),
            ))
        } else if selected {
            Line::from(Span::styled("·", Style::default().fg(YOU_C)))
        } else {
            Line::from("")
        };
        f.render_widget(
            Paragraph::new(content).alignment(Alignment::Center),
            inner,
        );
    }
}

fn tint_bg(v: f64) -> Color {
    let v = v.clamp(-1.0, 1.0);
    if v >= 0.0 {
        lerp(PANEL, Color::Rgb(30, 70, 45), v)
    } else {
        lerp(PANEL, Color::Rgb(80, 30, 45), -v)
    }
}

fn render_heaps(labels: &[String], counts: &[u32], max: u32, f: &mut Frame, area: Rect) {
    let mut lines: Vec<Line> = vec![Line::from("")];
    let nim_sum = counts.iter().fold(0u32, |a, &c| a ^ c);
    let barw = (area.width.saturating_sub(14)).min(28) as usize;
    for (i, &c) in counts.iter().enumerate() {
        let filled = if max == 0 {
            0
        } else {
            (c as usize * barw) / max as usize
        };
        let bar = format!("{}{}", "█".repeat(filled), "░".repeat(barw - filled));
        lines.push(Line::from(vec![
            Span::styled(
                format!("  {} ", labels.get(i).cloned().unwrap_or_default()),
                Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
            ),
            Span::styled(bar, Style::default().fg(OPP_C)),
            Span::styled(format!(" {c}"), Style::default().fg(TEXT)),
        ]));
    }
    lines.push(Line::from(""));
    let sum_color = if nim_sum == 0 { BAD } else { GOOD };
    lines.push(Line::from(vec![
        Span::styled("  nim-sum  ", Style::default().fg(MUTED)),
        Span::styled(
            format!("{} ⊕ {} ⊕ {} = {}", counts.first().copied().unwrap_or(0),
                counts.get(1).copied().unwrap_or(0),
                counts.get(2).copied().unwrap_or(0), nim_sum),
            Style::default().fg(sum_color).add_modifier(Modifier::BOLD),
        ),
    ]));
    lines.push(Line::from(Span::styled(
        if nim_sum == 0 {
            "  = 0 → the player to move is losing".to_string()
        } else {
            "  ≠ 0 → the player to move can force a win".to_string()
        },
        Style::default().fg(MUTED),
    )));
    f.render_widget(Paragraph::new(lines), area);
}

// ---- shared widgets -------------------------------------------------------- //
/// A labelled horizontal value bar in [-1, 1] (centre = 0).
pub fn value_bar(label: &str, v: f64, width: usize) -> Line<'static> {
    let w = width.max(4);
    let mid = w / 2;
    let pos = ((v.clamp(-1.0, 1.0) * mid as f64).round() as isize + mid as isize) as usize;
    let mut cells: Vec<char> = vec!['·'; w];
    cells[mid] = '┊';
    let p = pos.min(w - 1);
    cells[p] = '◆';
    let bar: String = cells.into_iter().collect();
    Line::from(vec![
        Span::styled(format!("{label:<7}"), Style::default().fg(MUTED)),
        Span::styled(bar, Style::default().fg(value_color(v))),
        Span::styled(format!(" {v:+.2}"), Style::default().fg(value_color(v))),
    ])
}

/// A win / draw / loss stacked bar.
pub fn outcome_bar(you: usize, draw: usize, opp: usize, width: usize) -> Line<'static> {
    let total = (you + draw + opp).max(1);
    let w = width.max(6);
    let yw = you * w / total;
    let dw = draw * w / total;
    let ow = w - yw - dw;
    Line::from(vec![
        Span::styled("█".repeat(yw), Style::default().fg(YOU_C)),
        Span::styled("█".repeat(dw), Style::default().fg(MUTED)),
        Span::styled("█".repeat(ow), Style::default().fg(OPP_C)),
    ])
}

// ---- overlays -------------------------------------------------------------- //
pub fn centered_rect(w: u16, h: u16, area: Rect) -> Rect {
    let w = w.min(area.width);
    let h = h.min(area.height);
    Rect {
        x: area.x + (area.width - w) / 2,
        y: area.y + (area.height - h) / 2,
        width: w,
        height: h,
    }
}

fn help_overlay(f: &mut Frame, area: Rect) {
    let rect = centered_rect(64, 22, area);
    f.render_widget(Clear, rect);
    let blk = panel("Help — high-level");
    let inner = blk.inner(rect);
    f.render_widget(blk, rect);

    let h = |k: &str, d: &str| {
        Line::from(vec![
            Span::styled(format!(" {k:<14}"), Style::default().fg(GOLD)),
            Span::styled(d.to_string(), Style::default().fg(TEXT)),
        ])
    };
    let sec = |t: &str| Line::from(Span::styled(format!(" {t}"), Style::default().fg(PICK_C).add_modifier(Modifier::BOLD)));
    let lines = vec![
        sec("Global"),
        h("1 / 2 / 3", "switch view: Strategy · Value-RL · Symmetry"),
        h("g", "switch game (Tic-Tac-Toe ↔ Nim)"),
        h("? · q", "this help · quit"),
        Line::from(""),
        sec("Strategy — discover & stack cards"),
        h("tab", "move focus between palette and your stack"),
        h("↑↓ / ⏎", "move cursor · add card / remove from stack"),
        h("[ ]", "reorder a stacked card up / down"),
        h("s", "scout: discover the highest-impact hidden card"),
        h("b · r · v", "cycle opponent · run 100 games · replay a game"),
        Line::from(""),
        sec("Value-RL — learn a value function"),
        h("space · t", "toggle self-play training · single step"),
        h("R", "reset the learner"),
        Line::from(""),
        sec("Value & Symmetry — explore positions"),
        h("↑↓ · ⏎ · u · n", "pick a move · play it · undo · new board"),
    ];
    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}

fn replay_overlay(app: &App, f: &mut Frame, area: Rect) {
    let Some(r) = app.replay.as_ref() else { return };
    let rect = centered_rect(46, 22, area);
    f.render_widget(Clear, rect);
    let blk = panel(&r.title);
    let inner = blk.inner(rect);
    f.render_widget(blk, rect);

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(4)])
        .split(inner);

    if let Some(frame) = r.frames.get(r.index) {
        render_sketch(&frame.sketch, &BoardOpts::plain(), f, rows[0]);
        let who = match frame.seat {
            Some(seat) => Span::styled(
                if seat == YOU { "You " } else { "Bot " },
                Style::default().fg(seat_color(seat)).add_modifier(Modifier::BOLD),
            ),
            None => Span::raw(""),
        };
        let cap = Line::from(vec![who, Span::styled(frame.caption.clone(), Style::default().fg(TEXT))]);
        let foot = Line::from(vec![
            Span::styled(
                format!("step {}/{}  ", r.index, r.frames.len().saturating_sub(1)),
                Style::default().fg(MUTED),
            ),
            Span::styled(format!("· {}", r.result), Style::default().fg(GOLD)),
        ]);
        f.render_widget(
            Paragraph::new(vec![Line::from(""), cap, foot]).alignment(Alignment::Center),
            rows[1],
        );
    }
}

#[cfg(test)]
mod render_tests {
    use super::*;
    use crate::app::{App, GameId, Tab};
    use crossterm::event::KeyCode;
    use ratatui::{backend::TestBackend, Terminal};

    fn render_text(app: &App, w: u16, h: u16) -> String {
        let mut term = Terminal::new(TestBackend::new(w, h)).unwrap();
        term.draw(|f| draw(app, f)).unwrap();
        let buf = term.backend().buffer();
        let area = buf.area;
        let mut out = String::new();
        for y in 0..area.height {
            for x in 0..area.width {
                out.push_str(buf.get(area.x + x, area.y + y).symbol());
            }
            out.push('\n');
        }
        out
    }

    /// A populated app, so every panel has real content to draw.
    fn busy_app() -> App {
        let mut app = App::new();
        app.ttt.scout();
        app.ttt.run_match();
        app.ttt.train_batch();
        app.nim.scout();
        app.nim.run_match();
        app
    }

    #[test]
    fn every_view_renders_for_both_games() {
        let mut app = busy_app();
        for game in [GameId::Ttt, GameId::Nim] {
            app.active = game;
            for tab in [Tab::Strategy, Tab::Value, Tab::Symmetry] {
                app.tab = tab;
                let txt = render_text(&app, 140, 44);
                assert!(txt.contains("high-level"), "header always present");
                assert!(txt.trim().lines().count() > 5, "view produced content");
            }
        }
    }

    #[test]
    fn view_specific_text_appears() {
        let mut app = busy_app();
        app.active = GameId::Ttt;

        app.tab = Tab::Strategy;
        let s = render_text(&app, 140, 44);
        assert!(s.contains("Your strategy") && s.contains("discovered"));

        app.tab = Tab::Value;
        let v = render_text(&app, 140, 44);
        assert!(v.contains("Self-play learner") && v.contains("Convergence"));

        app.tab = Tab::Symmetry;
        let y = render_text(&app, 140, 44);
        assert!(y.contains("real decisions") && y.contains("reduction factor"));
    }

    #[test]
    fn overlays_render_without_panic() {
        let mut app = busy_app();
        app.show_help = true;
        let h = render_text(&app, 120, 40);
        assert!(h.contains("Help"));
        app.show_help = false;
        // open the replay through the real key path (tab is Strategy, game Ttt)
        app.on_key(KeyCode::Char('v'));
        let r = render_text(&app, 120, 40);
        assert!(r.contains("replay"));
    }

    #[test]
    fn catan_view_renders_empty_and_populated_without_panic() {
        use crate::catan::{CatanState, PlayerInfo, SimResult, StepGame, Tile};

        let mut app = App::new();
        app.active = GameId::Catan;

        // Empty state (no server, no game, no sim) across all three tabs.
        for tab in [Tab::Strategy, Tab::Value, Tab::Symmetry] {
            app.tab = tab;
            let txt = render_text(&app, 140, 44);
            assert!(txt.contains("Catan"), "header shows the active game");
        }

        // Populate a simulation result and a live game, then re-render.
        app.catan.last_sim = Some(SimResult {
            games: 20,
            opponent: "VALUE".into(),
            you_wins: 12,
            opp_wins: 8,
            draws: 0,
            winrate: 0.6,
            avg_turns: 71.0,
            avg_your_vp: 8.4,
            avg_opp_vp: 7.1,
            offers: 30,
            accepts: 11,
            rejects: 14,
            confirms: 11,
            cancels: 3,
            vetoes: 2,
        });
        let tiles: Vec<Tile> = (0..19)
            .map(|i| Tile {
                resource: Some(["wood", "brick", "sheep", "wheat", "ore", "desert"][i % 6].into()),
                number: if i % 6 == 5 { None } else { Some((i % 11 + 2) as u64) },
            })
            .collect();
        let players = vec![
            PlayerInfo { color: "RED".into(), is_you: true, vp: 6, public_vp: 6, hand: [1, 2, 0, 3, 1], dev_cards: 1, longest_road: 4, strength: 0.62 },
            PlayerInfo { color: "BLUE".into(), is_you: false, vp: 5, public_vp: 5, hand: [0, 1, 2, 1, 0], dev_cards: 0, longest_road: 3, strength: 0.51 },
        ];
        app.catan.game = Some(StepGame {
            game_id: "g1".into(),
            seed: 42,
            state: CatanState {
                tiles,
                robber_tile: Some(9),
                num_buildings: 8,
                num_roads: 11,
                players,
                current_color: "RED".into(),
                prompt: "PLAY_TURN".into(),
                num_turns: 30,
                winner: None,
            },
            last_actor: Some("RED".into()),
            last_action: Some("RED: Build settlement [12]".into()),
            last_explanation: Some("[value] strength 0.62".into()),
            log: (0..40).map(|i| format!("line {i}")).collect(),
            done: false,
        });

        for &(w, h) in &[(8u16, 4u16), (24, 10), (60, 20), (140, 44), (200, 60)] {
            for tab in [Tab::Strategy, Tab::Value, Tab::Symmetry] {
                app.tab = tab;
                let _ = render_text(&app, w, h); // must not panic
            }
        }
    }

    #[test]
    fn renders_on_awkward_terminal_sizes_without_panic() {
        // The layout math (centering, cell sizing, charts) must never panic,
        // even on absurdly small or thin terminals.
        let app = busy_app();
        let mut app = app;
        for &(w, h) in &[(8u16, 4u16), (20, 8), (40, 12), (60, 20), (200, 60)] {
            for game in [GameId::Ttt, GameId::Nim] {
                app.active = game;
                for tab in [Tab::Strategy, Tab::Value, Tab::Symmetry] {
                    app.tab = tab;
                    let _ = render_text(&app, w, h); // must not panic
                }
            }
            app.show_help = true;
            let _ = render_text(&app, w, h);
            app.show_help = false;
        }
    }
}
