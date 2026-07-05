//! View 1 — Strategy: discover cards, stack a policy, simulate 100 games.

use ratatui::{prelude::*, widgets::*};

use super::*;
use crate::app::{Focus, Session};
use crate::cards::CardKind;
use crate::game::Game;

fn badge(kind: CardKind) -> Span<'static> {
    let (c, t) = match kind {
        CardKind::Pick => (PICK_C, "PICK"),
        CardKind::Avoid => (AVOID_C, "AVOID"),
    };
    Span::styled(format!(" {t} "), Style::default().fg(BG).bg(c).add_modifier(Modifier::BOLD))
}

pub fn render<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(36),
            Constraint::Percentage(28),
            Constraint::Percentage(36),
        ])
        .split(area);

    palette(s, f, cols[0]);
    stack(s, f, cols[1]);

    let right = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(8), Constraint::Min(7), Constraint::Length(6)])
        .split(cols[2]);
    opponent(s, f, right[0]);
    results(s, f, right[1]);
    log(s, f, right[2]);
}

fn palette<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let title = format!(
        "Cards — discovered {}/{}",
        s.discovered_count(),
        s.palette.len()
    );
    let focused = s.focus == Focus::Palette;
    let blk = panel_focused(&title, focused);
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let items: Vec<ListItem> = s
        .palette
        .iter()
        .map(|card| {
            if s.is_discovered(card.id) {
                let mut head = vec![
                    Span::styled(
                        format!("{} ", card.glyph),
                        Style::default().fg(GOLD).add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(
                        card.name.to_string(),
                        Style::default().fg(TEXT).add_modifier(Modifier::BOLD),
                    ),
                    Span::raw(" "),
                    badge(card.kind),
                ];
                if s.in_stack(card.id) {
                    head.push(Span::styled("  ✓ in stack", Style::default().fg(GOOD)));
                }
                ListItem::new(vec![
                    Line::from(head),
                    Line::from(Span::styled(format!("   {}", card.blurb), Style::default().fg(MUTED))),
                ])
            } else {
                ListItem::new(vec![
                    Line::from(vec![
                        Span::styled("▓ ", Style::default().fg(BORDER_HI)),
                        Span::styled("??? hidden strategy", Style::default().fg(BORDER_HI)),
                    ]),
                    Line::from(Span::styled("   scout [s] to reveal", Style::default().fg(BORDER))),
                ])
            }
        })
        .collect();

    let list = List::new(items).highlight_style(
        Style::default().bg(Color::Rgb(40, 46, 78)).add_modifier(Modifier::BOLD),
    );
    let mut state = ListState::default();
    if focused {
        state.select(Some(s.palette_cursor.min(s.palette.len().saturating_sub(1))));
    }
    f.render_stateful_widget(list, inner, &mut state);
}

fn stack<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let focused = s.focus == Focus::Stack;
    let blk = panel_focused("Your strategy", focused);
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(2)])
        .split(inner);

    if s.stack.is_empty() {
        f.render_widget(
            Paragraph::new(vec![
                Line::from(""),
                Line::from(Span::styled("  no cards yet", Style::default().fg(MUTED))),
                Line::from(Span::styled("  → you would play pure random.", Style::default().fg(MUTED))),
                Line::from(""),
                Line::from(Span::styled("  Focus the palette [tab],", Style::default().fg(MUTED))),
                Line::from(Span::styled("  add cards [⏎], scout [s].", Style::default().fg(MUTED))),
            ])
            .wrap(Wrap { trim: true }),
            rows[0],
        );
    } else {
        let items: Vec<ListItem> = s
            .stack
            .iter()
            .enumerate()
            .map(|(i, id)| {
                let card = s.palette.iter().find(|c| c.id == *id).unwrap();
                ListItem::new(Line::from(vec![
                    Span::styled(
                        format!(" {} ", i + 1),
                        Style::default().fg(BG).bg(YOU_C).add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(format!(" {} ", card.glyph), Style::default().fg(GOLD)),
                    Span::styled(card.name.to_string(), Style::default().fg(TEXT)),
                    Span::raw(" "),
                    badge(card.kind),
                ]))
            })
            .collect();
        let list = List::new(items).highlight_style(
            Style::default().bg(Color::Rgb(40, 46, 78)).add_modifier(Modifier::BOLD),
        );
        let mut state = ListState::default();
        if focused {
            state.select(Some(s.stack_cursor.min(s.stack.len().saturating_sub(1))));
        }
        f.render_stateful_widget(list, rows[0], &mut state);
    }

    f.render_widget(
        Paragraph::new(vec![Line::from(vec![
            Span::styled(" ∞ ", Style::default().fg(BG).bg(MUTED)),
            Span::styled(" 🎲 random fallback", Style::default().fg(MUTED)),
        ])]),
        rows[1],
    );
}

fn opponent<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("Opponent");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let bot = s.bot();
    let beaten = s.beaten.iter().any(|b| *b == bot.key);

    let mut lines = vec![Line::from(vec![
        Span::styled(bot.name.to_string(), Style::default().fg(OPP_C).add_modifier(Modifier::BOLD)),
        Span::styled(format!("  {}", stars(bot.stars)), Style::default().fg(GOLD)),
        if beaten {
            Span::styled("  🏅 beaten", Style::default().fg(GOOD))
        } else {
            Span::raw("")
        },
    ])];
    lines.push(Line::from(Span::styled(bot.desc.to_string(), Style::default().fg(MUTED))));
    let their: Vec<Span> = if bot.rule_ids.is_empty() {
        vec![Span::styled("🎲 pure random", Style::default().fg(MUTED))]
    } else {
        bot.rule_ids
            .iter()
            .flat_map(|id| {
                let card = s.palette.iter().find(|c| c.id == *id).unwrap();
                let lock = if s.is_discovered(id) { "" } else { "🔒" };
                vec![Span::styled(
                    format!("{}{} ", lock, card.glyph),
                    Style::default().fg(TEXT),
                )]
            })
            .collect()
    };
    lines.push(Line::from(Span::styled("their stack: ", Style::default().fg(MUTED))));
    lines.push(Line::from(their));
    lines.push(Line::from(Span::styled(
        "[b] cycle opponent   [r] run 100 games",
        Style::default().fg(MUTED),
    )));
    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}

fn results<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("Match results");
    let inner = blk.inner(area);
    f.render_widget(blk, area);

    let Some(m) = s.last.as_ref() else {
        f.render_widget(
            Paragraph::new(vec![
                Line::from(""),
                Line::from(Span::styled("  Press [r] to simulate", Style::default().fg(TEXT))),
                Line::from(Span::styled("  100 games against the", Style::default().fg(TEXT))),
                Line::from(Span::styled("  selected opponent.", Style::default().fg(TEXT))),
                Line::from(""),
                Line::from(Span::styled("  Whoever wins more games", Style::default().fg(MUTED))),
                Line::from(Span::styled("  wins the match.", Style::default().fg(MUTED))),
            ]),
            inner,
        );
        return;
    };
    let st = &m.stats;
    let (banner, bcol) = if st.you > st.opp {
        ("🏆 You win the match!", YOU_C)
    } else if st.you < st.opp {
        ("🤖 Opponent wins", OPP_C)
    } else {
        ("🤝 Dead heat", MUTED)
    };

    let width = inner.width.saturating_sub(2) as usize;
    let mom_min = *st.momentum.iter().min().unwrap_or(&0);
    let mom_data: Vec<u64> = st.momentum.iter().map(|v| (*v - mom_min) as u64).collect();

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(2),
            Constraint::Min(0),
        ])
        .split(inner);

    f.render_widget(
        Paragraph::new(Line::from(Span::styled(
            banner,
            Style::default().fg(bcol).add_modifier(Modifier::BOLD),
        ))),
        rows[0],
    );
    f.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled(format!("{}", st.you), Style::default().fg(YOU_C).add_modifier(Modifier::BOLD)),
            Span::styled(" : ", Style::default().fg(MUTED)),
            Span::styled(format!("{}", st.opp), Style::default().fg(OPP_C).add_modifier(Modifier::BOLD)),
            Span::styled(format!("   ({} draws)", st.draws), Style::default().fg(MUTED)),
        ])),
        rows[1],
    );
    f.render_widget(Paragraph::new(outcome_bar(st.you, st.draws, st.opp, width)), rows[2]);
    f.render_widget(
        Paragraph::new(vec![
            Line::from(Span::styled(
                format!(
                    "avg {:.1} moves · streaks you {} / opp {}",
                    st.avg_turns, st.max_streak_you, st.max_streak_opp
                ),
                Style::default().fg(MUTED),
            )),
            Line::from(Span::styled(
                format!(
                    "first-move: started {}→{}W · second {}→{}W",
                    st.you_start_games, st.you_start_wins, st.you_second_games, st.you_second_wins
                ),
                Style::default().fg(MUTED),
            )),
        ]),
        rows[3],
    );
    let spark = Sparkline::default()
        .block(
            Block::default().title(Span::styled(
                "momentum (your cumulative lead) · [v] replay",
                Style::default().fg(MUTED),
            )),
        )
        .data(&mom_data)
        .style(Style::default().fg(if st.you >= st.opp { YOU_C } else { OPP_C }));
    f.render_widget(spark, rows[4]);
}

fn log<G: Game>(s: &Session<G>, f: &mut Frame, area: Rect) {
    let blk = panel("Lab log");
    let inner = blk.inner(area);
    f.render_widget(blk, area);
    let h = inner.height as usize;
    let start = s.log.len().saturating_sub(h);
    let lines: Vec<Line> = s.log[start..]
        .iter()
        .map(|l| Line::from(Span::styled(l.clone(), Style::default().fg(MUTED))))
        .collect();
    f.render_widget(Paragraph::new(lines).wrap(Wrap { trim: true }), inner);
}
