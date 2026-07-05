//! View 2 — Value-RL: a tabular value function learned by self-play, watched
//! as it converges to the exact minimax values.

use ratatui::{prelude::*, widgets::*};

use super::*;
use crate::app::Session;
use crate::game::Game;

pub fn render<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(44), Constraint::Percentage(56)])
        .split(area);

    left(s, f, cols[0]);
    right(s, f, cols[1]);
}

fn left<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(12), Constraint::Min(5), Constraint::Length(5)])
        .split(area);

    // board with the learned-value heatmap
    let blk = panel("Position — learned value heatmap");
    let inner = blk.inner(rows[0]);
    f.render_widget(blk, rows[0]);
    let opts = BoardOpts {
        selected_cell: s.selected_cell(),
        cell_values: grid_cell_values(s, &s.learned_vals),
        tint: true,
    };
    render_sketch(&s.sketch(), &opts, f, inner);

    // per-move value list: exact vs learned
    move_list(s, f, rows[1]);

    // explore info
    let blk = panel("This position");
    let inner = blk.inner(rows[2]);
    f.render_widget(blk, rows[2]);
    let info = if s.terminal() {
        let w = match s.explore_winner() {
            Some(seat) => Span::styled(
                if seat == YOU { "You win" } else { "Opponent wins" },
                Style::default().fg(seat_color(seat)).add_modifier(Modifier::BOLD),
            ),
            None => Span::styled("Draw", Style::default().fg(MUTED)),
        };
        vec![Line::from(vec![Span::styled("terminal · ", Style::default().fg(MUTED)), w])]
    } else {
        vec![
            Line::from(vec![
                Span::styled("to move: ", Style::default().fg(MUTED)),
                Span::styled(
                    if s.explore_current() == YOU { "You" } else { "Opponent" },
                    Style::default().fg(seat_color(s.explore_current())).add_modifier(Modifier::BOLD),
                ),
            ]),
            super::value_bar("exact", s.explore_optimal, 16),
            super::value_bar("learned", s.explore_learned, 16),
        ]
    };
    f.render_widget(Paragraph::new(info), inner);
}

fn move_list<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("Move values — exact ┊ learned");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    if s.terminal() {
        f.render_widget(
            Paragraph::new(Span::styled("  game over — [n] new board", Style::default().fg(MUTED))),
            inner,
        );
        return;
    }

    let items: Vec<ListItem> = s
        .exact_vals
        .iter()
        .zip(&s.learned_vals)
        .map(|((mv, ev), (_, lv))| {
            let label = s.game.move_label(&s.explore, mv);
            let optimal = (*ev - s.explore_optimal).abs() < 1e-9;
            let star = if optimal {
                Span::styled(" ★", Style::default().fg(GOLD))
            } else {
                Span::raw("  ")
            };
            ListItem::new(Line::from(vec![
                Span::styled(format!("{label:<14}"), Style::default().fg(TEXT)),
                Span::styled(format!("{ev:+.2}", ev = ev), Style::default().fg(value_color(*ev))),
                Span::styled(" ┊ ", Style::default().fg(BORDER)),
                Span::styled(format!("{lv:+.2}", lv = lv), Style::default().fg(value_color(*lv))),
                star,
            ]))
        })
        .collect();

    let list = List::new(items)
        .highlight_style(Style::default().bg(Color::Rgb(40, 46, 78)).add_modifier(Modifier::BOLD))
        .highlight_symbol("▸ ");
    let mut state = ListState::default();
    state.select(Some(s.move_cursor.min(s.exact_vals.len().saturating_sub(1))));
    f.render_stateful_widget(list, inner, &mut state);
}

fn right<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(7), Constraint::Min(6), Constraint::Length(6)])
        .split(area);

    stats(s, f, rows[0]);
    chart(s, f, rows[1]);
    eval(s, f, rows[2]);
}

fn stats<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("Self-play learner");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let m = s.learner.latest();
    let auto = if s.auto_train {
        Span::styled(" ● TRAINING ", Style::default().fg(BG).bg(GOOD).add_modifier(Modifier::BOLD))
    } else {
        Span::styled(" ○ paused ", Style::default().fg(MUTED))
    };
    let lines = vec![
        Line::from(vec![
            auto,
            Span::styled(
                format!("   {} episodes", m.episodes),
                Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
            ),
        ]),
        Line::from(vec![
            Span::styled("error to optimal (MAE): ", Style::default().fg(MUTED)),
            Span::styled(format!("{:.3}", m.mae), Style::default().fg(value_color(1.0 - m.mae * 2.0))),
        ]),
        Line::from(vec![
            Span::styled("V(start) learned ", Style::default().fg(MUTED)),
            Span::styled(format!("{:+.2}", m.root_value), Style::default().fg(value_color(m.root_value))),
            Span::styled("   ε ", Style::default().fg(MUTED)),
            Span::styled(format!("{:.2}", m.epsilon), Style::default().fg(TEXT)),
        ]),
        Line::from(vec![
            Span::styled("states learned ", Style::default().fg(MUTED)),
            Span::styled(
                format!("{} / {}", s.table_size(), s.learner.domain_size()),
                Style::default().fg(TEXT),
            ),
            Span::styled("  (symmetry-folded)", Style::default().fg(MUTED)),
        ]),
    ];
    f.render_widget(Paragraph::new(lines), inner);
}

fn chart<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let hist = &s.learner.history;
    let mae: Vec<(f64, f64)> =
        hist.iter().map(|m| (m.episodes as f64, m.mae)).collect();
    let loss: Vec<(f64, f64)> =
        hist.iter().map(|m| (m.episodes as f64, m.eval_loss)).collect();
    let xmax = hist.last().map(|m| m.episodes as f64).unwrap_or(1.0).max(1.0);
    let ymax = mae.iter().map(|p| p.1).fold(0.1f64, f64::max).max(0.1);

    let datasets = vec![
        Dataset::default()
            .name("MAE → optimal")
            .marker(symbols::Marker::Braille)
            .graph_type(GraphType::Line)
            .style(Style::default().fg(GOLD))
            .data(&mae),
        Dataset::default()
            .name("loss vs random")
            .marker(symbols::Marker::Braille)
            .graph_type(GraphType::Line)
            .style(Style::default().fg(AVOID_C))
            .data(&loss),
    ];
    let chart = Chart::new(datasets)
        .block(panel("Convergence"))
        .x_axis(
            Axis::default()
                .style(Style::default().fg(MUTED))
                .bounds([0.0, xmax])
                .labels(vec![
                    Span::styled("0", Style::default().fg(MUTED)),
                    Span::styled(format!("{} ep", xmax as usize), Style::default().fg(MUTED)),
                ]),
        )
        .y_axis(
            Axis::default()
                .style(Style::default().fg(MUTED))
                .bounds([0.0, ymax])
                .labels(vec![
                    Span::styled("0", Style::default().fg(MUTED)),
                    Span::styled(format!("{ymax:.2}"), Style::default().fg(MUTED)),
                ]),
        );
    f.render_widget(chart, area);
}

fn eval<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("Greedy policy vs random opponent");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let m = s.learner.latest();
    let w = inner.width.saturating_sub(2) as usize;
    let pct = |x: f64| (x * 100.0).round() as i32;
    let lines = vec![
        outcome_bar(
            (m.eval_win * 1000.0) as usize,
            (m.eval_draw * 1000.0) as usize,
            (m.eval_loss * 1000.0) as usize,
            w,
        ),
        Line::from(vec![
            Span::styled(format!("win {}%  ", pct(m.eval_win)), Style::default().fg(YOU_C)),
            Span::styled(format!("draw {}%  ", pct(m.eval_draw)), Style::default().fg(MUTED)),
            Span::styled(format!("loss {}%", pct(m.eval_loss)), Style::default().fg(OPP_C)),
        ]),
        Line::from(Span::styled(
            "[space] auto-train   [t] +150 episodes   [R] reset",
            Style::default().fg(MUTED),
        )),
    ];
    f.render_widget(Paragraph::new(lines), inner);
}
