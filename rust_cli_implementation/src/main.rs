//! Entry point. `high-level` runs the interactive TUI; `high-level selftest`
//! runs a headless check that exercises every view and the learning loop.

use std::io::{self, Stdout};
use std::time::Duration;

use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};

use high_level::app::App;
use high_level::{selftest, ui};

fn main() -> io::Result<()> {
    if std::env::args().any(|a| a == "selftest" || a == "--selftest") {
        return selftest::run();
    }
    run_tui()
}

fn restore_terminal() {
    let _ = disable_raw_mode();
    let _ = execute!(io::stdout(), LeaveAlternateScreen);
}

fn run_tui() -> io::Result<()> {
    // Make sure a panic leaves the terminal usable.
    let prev = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        restore_terminal();
        prev(info);
    }));

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let mut terminal: Terminal<CrosstermBackend<Stdout>> =
        Terminal::new(CrosstermBackend::new(stdout))?;

    let res = event_loop(&mut terminal);

    restore_terminal();
    res
}

fn event_loop(terminal: &mut Terminal<CrosstermBackend<Stdout>>) -> io::Result<()> {
    let mut app = App::new();
    while !app.should_quit {
        terminal.draw(|f| ui::draw(&app, f))?;

        // Poll briefly while auto-training so the learning animates; otherwise
        // block longer to stay idle-cheap.
        let timeout = if app.auto_training() {
            Duration::from_millis(25)
        } else {
            Duration::from_millis(200)
        };

        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                if matches!(key.kind, KeyEventKind::Press | KeyEventKind::Repeat) {
                    if key.modifiers.contains(KeyModifiers::CONTROL)
                        && matches!(key.code, KeyCode::Char('c'))
                    {
                        app.should_quit = true;
                    } else {
                        app.on_key(key.code);
                    }
                }
            }
        } else {
            app.tick();
        }
    }
    Ok(())
}
