//! View 3 — Symmetry: fold the game by its group. The legal moves collapse to
//! the few genuine decisions, and the whole state space shrinks by the group
//! order — which is exactly why the value table (view 2) is so small.

use ratatui::{prelude::*, widgets::*};

use super::*;
use crate::app::Session;
use crate::game::Game;

pub fn render<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(34),
            Constraint::Percentage(34),
            Constraint::Percentage(32),
        ])
        .split(area);

    left(s, f, cols[0]);
    core_decisions(s, f, cols[1]);

    let right = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(10), Constraint::Min(8)])
        .split(cols[2]);
    orbit(s, f, right[0]);
    reduction(s, f, right[1]);
}

fn left<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(12), Constraint::Min(4), Constraint::Length(4)])
        .split(area);

    let blk = panel("Explore a position");
    let inner = blk.inner(rows[0]);
    f.render_widget(blk, rows[0]);
    let opts = BoardOpts {
        selected_cell: s.selected_cell(),
        cell_values: vec![],
        tint: false,
    };
    render_sketch(&s.sketch(), &opts, f, inner);

    // move list with exact values (so "core decisions" can be read against them)
    let blk = panel("Legal moves (exact value)");
    let inner = blk.inner(rows[1]);
    f.render_widget(blk, rows[1]);
    if s.terminal() {
        f.render_widget(
            Paragraph::new(Span::styled("  terminal — [n] new board", Style::default().fg(MUTED))),
            inner,
        );
    } else {
        let items: Vec<ListItem> = s
            .exact_vals
            .iter()
            .map(|(mv, ev)| {
                let optimal = (*ev - s.explore_optimal).abs() < 1e-9;
                ListItem::new(Line::from(vec![
                    Span::styled(
                        format!("{:<14}", s.game.move_label(&s.explore, mv)),
                        Style::default().fg(TEXT),
                    ),
                    Span::styled(format!("{ev:+.2}"), Style::default().fg(value_color(*ev))),
                    if optimal {
                        Span::styled(" ★", Style::default().fg(GOLD))
                    } else {
                        Span::raw("")
                    },
                ]))
            })
            .collect();
        let list = List::new(items)
            .highlight_style(Style::default().bg(Color::Rgb(40, 46, 78)))
            .highlight_symbol("▸ ");
        let mut state = ListState::default();
        state.select(Some(s.move_cursor.min(s.exact_vals.len().saturating_sub(1))));
        f.render_stateful_widget(list, inner, &mut state);
    }

    let blk = panel("Fingerprints");
    let inner = blk.inner(rows[2]);
    f.render_widget(blk, rows[2]);
    f.render_widget(
        Paragraph::new(vec![
            Line::from(vec![
                Span::styled("raw key       ", Style::default().fg(MUTED)),
                Span::styled(format!("{}", s.current_key), Style::default().fg(TEXT)),
            ]),
            Line::from(vec![
                Span::styled("canonical key ", Style::default().fg(MUTED)),
                Span::styled(format!("{}", s.canonical_key), Style::default().fg(GOLD)),
            ]),
        ]),
        inner,
    );
}

fn core_decisions<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("The core decision");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    if s.terminal() {
        f.render_widget(
            Paragraph::new(Span::styled("  no moves — terminal position", Style::default().fg(MUTED))),
            inner,
        );
        return;
    }

    let legal: usize = s.classes.iter().map(|c| c.size).sum();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(0)])
        .split(inner);

    f.render_widget(
        Paragraph::new(vec![
            Line::from(vec![
                Span::styled(format!("{legal}"), Style::default().fg(TEXT).add_modifier(Modifier::BOLD)),
                Span::styled(" legal moves  →  ", Style::default().fg(MUTED)),
                Span::styled(
                    format!("{}", s.classes.len()),
                    Style::default().fg(GOLD).add_modifier(Modifier::BOLD),
                ),
                Span::styled(" real decisions", Style::default().fg(MUTED)),
            ]),
            Line::from(Span::styled(
                "moves that lead to symmetric positions are one choice:",
                Style::default().fg(MUTED),
            )),
        ])
        .wrap(Wrap { trim: true }),
        rows[0],
    );

    let items: Vec<ListItem> = s
        .classes
        .iter()
        .map(|c| {
            let star = if c.is_optimal {
                Span::styled(" ★ best", Style::default().fg(GOLD))
            } else {
                Span::raw("")
            };
            let head = Line::from(vec![
                Span::styled(
                    format!("{} ", c.rep),
                    Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
                ),
                Span::styled(format!("×{}", c.size), Style::default().fg(OPP_C)),
                Span::styled("   value ", Style::default().fg(MUTED)),
                Span::styled(format!("{:+.2}", c.exact_value), Style::default().fg(value_color(c.exact_value))),
                star,
            ]);
            let members = Line::from(Span::styled(
                format!("   = {{ {} }}", c.members.join(", ")),
                Style::default().fg(MUTED),
            ));
            ListItem::new(vec![head, members])
        })
        .collect();
    f.render_widget(List::new(items), rows[1]);
}

fn orbit<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let title = format!("Orbit — {} of {} symmetries", s.orbit.len(), s.sym.group_order);
    let blk = panel(&title);
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    if s.orbit.is_empty() {
        return;
    }
    let n = s.orbit.len();
    let fit = ((inner.width as usize) / 9).clamp(1, n);
    let constraints: Vec<Constraint> = (0..fit).map(|_| Constraint::Ratio(1, fit as u32)).collect();
    let cells = Layout::default()
        .direction(Direction::Horizontal)
        .constraints(constraints)
        .split(inner);
    for i in 0..fit {
        let sub = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(0), Constraint::Length(1)])
            .split(cells[i]);
        render_sketch(&s.orbit[i].sketch, &BoardOpts::plain(), f, sub[0]);
        let tag = if s.orbit[i].is_identity { "this" } else { "≡" };
        f.render_widget(
            Paragraph::new(Span::styled(tag, Style::default().fg(MUTED))).alignment(Alignment::Center),
            sub[1],
        );
    }
}

fn reduction<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("State-space reduction");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let st = &s.sym;

    let mut lines = vec![
        Line::from(vec![
            Span::styled("reachable positions  ", Style::default().fg(MUTED)),
            Span::styled(format!("{}", st.reachable), Style::default().fg(TEXT).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::styled("distinct under group ", Style::default().fg(MUTED)),
            Span::styled(format!("{}", st.canonical), Style::default().fg(GOLD).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::styled("reduction factor     ", Style::default().fg(MUTED)),
            Span::styled(format!("{:.2}×", st.reduction()), Style::default().fg(GOOD).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::styled("group order          ", Style::default().fg(MUTED)),
            Span::styled(format!("{}", st.group_order), Style::default().fg(TEXT)),
        ]),
        Line::from(""),
        Line::from(Span::styled("per ply  raw → folded", Style::default().fg(MUTED))),
    ];
    for (d, raw, can) in st.by_depth.iter().take(inner.height.saturating_sub(7) as usize) {
        lines.push(Line::from(vec![
            Span::styled(format!("  {d:>2}  "), Style::default().fg(MUTED)),
            Span::styled(format!("{raw:>5}"), Style::default().fg(TEXT)),
            Span::styled(" → ", Style::default().fg(BORDER)),
            Span::styled(format!("{can:<5}"), Style::default().fg(GOLD)),
        ]));
    }
    lines.push(Line::from(Span::styled(
        "↳ that's why the value table is small.",
        Style::default().fg(MUTED),
    )));
    f.render_widget(Paragraph::new(lines), inner);
}
