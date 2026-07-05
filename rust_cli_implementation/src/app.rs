//! Application state — UI-agnostic. `main` drives input → these methods →
//! `ui` renders the result. A `Session<G>` holds one game's state across all
//! three views; `App` owns one session per game plus the global chrome.

use crossterm::event::KeyCode;

use crate::cards::{Card, CardKind};
use crate::catan::CatanLab;
use crate::engine::{compute_stats, replay_game, simulate_match, GameResult, MatchStats};
use crate::game::{terminal_value, BoardSketch, Game, Nim, Seat, TicTacToe, YOU};
use crate::rl::{QLearner, Solver};
use crate::rng::Rng;
use crate::symmetry::{self, SymStats};

pub const EPISODES_PER_BATCH: usize = 150;
const MATCH_GAMES: usize = 100;
const SCOUT_GAMES: usize = 40;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Strategy,
    Value,
    Symmetry,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum GameId {
    Ttt,
    Nim,
    /// Not a `Game` — too big to solve. A bridge to the real catanatron engine,
    /// where you tune a policy instead of stacking cards. See `crate::catan`.
    Catan,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Focus {
    Palette,
    Stack,
}

#[derive(Clone)]
pub struct BotPreset {
    pub name: &'static str,
    pub key: &'static str,
    pub stars: u8,
    pub desc: &'static str,
    pub rule_ids: Vec<&'static str>,
}

/// A symmetry-equivalent class of moves — one genuine decision.
#[derive(Clone)]
pub struct ClassDisplay {
    pub rep: String,
    pub members: Vec<String>,
    pub size: usize,
    pub exact_value: f64,
    pub is_optimal: bool,
    pub after: BoardSketch,
}

/// One member of the current position's symmetry orbit.
#[derive(Clone)]
pub struct OrbitDisplay {
    pub group_label: String,
    pub sketch: BoardSketch,
    pub is_identity: bool,
}

/// A finished match, kept for the results panel and replay viewer.
pub struct MatchView {
    pub stats: MatchStats,
    pub results: Vec<GameResult>,
    pub you_ids: Vec<String>,
    pub opp_ids: Vec<String>,
    pub base_seed: u32,
    pub bot_name: &'static str,
    pub bot_stars: u8,
}

pub struct Session<G: Game> {
    pub game: G,
    pub palette: Vec<Card<G>>,
    pub bots: Vec<BotPreset>,

    // strategy / discovery
    pub discovered: Vec<&'static str>,
    pub stack: Vec<&'static str>,
    pub beaten: Vec<&'static str>,
    pub selected_bot: usize,
    pub focus: Focus,
    pub palette_cursor: usize,
    pub stack_cursor: usize,
    pub log: Vec<String>,
    pub last: Option<MatchView>,

    // value-function RL
    pub solver: Solver,
    pub learner: QLearner<G>,
    pub auto_train: bool,

    // shared explore board (value + symmetry views)
    pub explore: G::State,
    pub trail: Vec<G::State>,
    pub move_cursor: usize,
    pub sym: SymStats,

    // caches refreshed whenever the explore board or learner changes
    pub exact_vals: Vec<(G::Move, f64)>,
    pub learned_vals: Vec<(G::Move, f64)>,
    pub classes: Vec<ClassDisplay>,
    pub orbit: Vec<OrbitDisplay>,
    pub canonical_sketch: BoardSketch,
    pub explore_optimal: f64,
    pub explore_learned: f64,
    pub current_key: u64,
    pub canonical_key: u64,

    base_seed: u32,
    match_counter: u32,
}

impl<G: Game> Session<G> {
    pub fn new(game: G, palette: Vec<Card<G>>, bots: Vec<BotPreset>, seed: u32) -> Self {
        let mut rng = Rng::new(seed);
        let explore = game.initial(&mut rng, YOU);
        let sym = symmetry::analyze(&game);
        let learner = QLearner::new(&game, seed ^ 0x5151_5151);
        let discovered = palette.first().map(|c| vec![c.id]).unwrap_or_default();

        let mut s = Session {
            game,
            palette,
            bots,
            discovered,
            stack: vec![],
            beaten: vec![],
            selected_bot: 0,
            focus: Focus::Palette,
            palette_cursor: 0,
            stack_cursor: 0,
            log: vec![
                "Welcome. Scout [s] to discover strategies; stack them; Run [r] a match.".into(),
            ],
            last: None,
            solver: Solver::new(),
            learner,
            auto_train: false,
            explore,
            trail: vec![],
            move_cursor: 0,
            sym,
            exact_vals: vec![],
            learned_vals: vec![],
            classes: vec![],
            orbit: vec![],
            canonical_sketch: BoardSketch::Grid { cols: 1, cells: vec![] },
            explore_optimal: 0.0,
            explore_learned: 0.0,
            current_key: 0,
            canonical_key: 0,
            base_seed: seed,
            match_counter: 0,
        };
        s.refresh();
        s
    }

    // ---- shared explore board ------------------------------------------- //
    pub fn legal(&self) -> Vec<G::Move> {
        self.game.legal_moves(&self.explore)
    }
    pub fn terminal(&self) -> bool {
        self.game.is_terminal(&self.explore)
    }

    fn refresh(&mut self) {
        let terminal = self.game.is_terminal(&self.explore);
        let legal = self.game.legal_moves(&self.explore);
        if self.move_cursor >= legal.len() {
            self.move_cursor = 0;
        }

        // exact + learned value of each legal move (value to the mover)
        self.exact_vals = if terminal {
            vec![]
        } else {
            self.solver.move_values(&self.game, &self.explore)
        };
        self.learned_vals = if terminal {
            vec![]
        } else {
            self.learner.move_values(&self.game, &self.explore)
        };
        self.explore_optimal = if terminal {
            terminal_value(&self.game, &self.explore)
        } else {
            self.solver.value(&self.game, &self.explore)
        };
        self.explore_learned = if terminal {
            terminal_value(&self.game, &self.explore)
        } else {
            self.learned_vals
                .iter()
                .map(|(_, v)| *v)
                .fold(f64::NEG_INFINITY, f64::max)
        };

        // symmetry: move classes (the core decisions) with exact values
        let raw_classes = symmetry::move_classes(&self.game, &self.explore);
        let mut classes: Vec<ClassDisplay> = raw_classes
            .iter()
            .map(|c| {
                let value = -self.solver.value(&self.game, &c.after_canonical);
                ClassDisplay {
                    rep: self.game.move_label(&self.explore, &c.representative),
                    members: c
                        .members
                        .iter()
                        .map(|m| self.game.move_label(&self.explore, m))
                        .collect(),
                    size: c.members.len(),
                    exact_value: value,
                    is_optimal: false,
                    after: self.game.sketch(&c.after_canonical),
                }
            })
            .collect();
        let best = classes.iter().map(|c| c.exact_value).fold(f64::NEG_INFINITY, f64::max);
        for c in classes.iter_mut() {
            c.is_optimal = (c.exact_value - best).abs() < 1e-9;
        }
        self.classes = classes;

        // symmetry: the orbit (distinct symmetric images of this position)
        self.orbit = symmetry::orbit(&self.game, &self.explore)
            .iter()
            .map(|m| OrbitDisplay {
                group_label: self.game.group_label(m.group_index),
                sketch: self.game.sketch(&m.state),
                is_identity: m.group_index == 0,
            })
            .collect();

        let canon = symmetry::canonical_state(&self.game, &self.explore);
        self.canonical_sketch = self.game.sketch(&canon);
        self.current_key = self.game.key(&self.explore);
        self.canonical_key = symmetry::canonical_key(&self.game, &self.explore);
    }

    pub fn sketch(&self) -> BoardSketch {
        self.game.sketch(&self.explore)
    }
    pub fn explore_current(&self) -> Seat {
        self.game.current(&self.explore)
    }
    pub fn explore_winner(&self) -> Option<Seat> {
        self.game.winner(&self.explore)
    }
    pub fn selected_move(&self) -> Option<G::Move> {
        self.legal().get(self.move_cursor).cloned()
    }
    pub fn selected_cell(&self) -> Option<usize> {
        self.selected_move()
            .and_then(|m| self.game.move_cell(&self.explore, &m))
    }

    fn move_cursor_step(&mut self, delta: isize) {
        let n = self.legal().len();
        if n == 0 {
            return;
        }
        let cur = self.move_cursor as isize;
        self.move_cursor = (cur + delta).rem_euclid(n as isize) as usize;
    }
    fn play_selected(&mut self) {
        if let Some(mv) = self.selected_move() {
            let mut rng = Rng::new(0);
            let next = self.game.apply(&self.explore, Some(&mv), &mut rng);
            self.trail.push(self.explore.clone());
            self.explore = next;
            self.move_cursor = 0;
            self.refresh();
        }
    }
    fn undo(&mut self) {
        if let Some(prev) = self.trail.pop() {
            self.explore = prev;
            self.move_cursor = 0;
            self.refresh();
        }
    }
    fn reset_explore(&mut self) {
        let mut rng = Rng::new(self.base_seed);
        self.explore = self.game.initial(&mut rng, YOU);
        self.trail.clear();
        self.move_cursor = 0;
        self.refresh();
    }

    // ---- strategy / discovery ------------------------------------------- //
    pub fn is_discovered(&self, id: &str) -> bool {
        self.discovered.iter().any(|d| *d == id)
    }
    pub fn in_stack(&self, id: &str) -> bool {
        self.stack.iter().any(|d| *d == id)
    }
    pub fn bot(&self) -> &BotPreset {
        &self.bots[self.selected_bot]
    }
    pub fn discovered_count(&self) -> usize {
        self.discovered.len()
    }

    fn reveal(&mut self, id: &'static str) -> bool {
        if !self.is_discovered(id) {
            self.discovered.push(id);
            true
        } else {
            false
        }
    }

    /// Estimate a card's marginal win-rate when appended to the current stack.
    fn trial_winrate(&self, extra: Option<&'static str>) -> f64 {
        let mut you: Vec<String> = self.stack.iter().map(|s| s.to_string()).collect();
        if let Some(id) = extra {
            if !you.iter().any(|s| s == id) {
                you.push(id.to_string());
            }
        }
        let opp: Vec<String> = self.bot().rule_ids.iter().map(|s| s.to_string()).collect();
        let results = simulate_match(
            &self.game,
            &self.palette,
            &you,
            &opp,
            SCOUT_GAMES,
            0x5C00 ^ (self.selected_bot as u32),
        );
        let st = compute_stats(&results);
        st.you as f64 / SCOUT_GAMES as f64
    }

    /// Discover the highest-impact card not yet found — measured by simulation.
    pub fn scout(&mut self) {
        let undiscovered: Vec<&'static str> = self
            .palette
            .iter()
            .map(|c| c.id)
            .filter(|id| !self.is_discovered(id))
            .collect();
        if undiscovered.is_empty() {
            self.log_line("All strategies already discovered — the palette is complete.".into());
            return;
        }
        let base = self.trial_winrate(None);
        let mut best: Option<(&'static str, f64)> = None;
        for id in undiscovered {
            let wr = self.trial_winrate(Some(id));
            let delta = wr - base;
            if best.map_or(true, |(_, d)| delta > d) {
                best = Some((id, delta));
            }
        }
        if let Some((id, delta)) = best {
            self.reveal(id);
            let card = self.palette.iter().find(|c| c.id == id).unwrap();
            let pct = (delta * 100.0).round() as i32;
            let sign = if pct >= 0 { "+" } else { "" };
            self.log_line(format!(
                "Scouted {} {} [{}] — {}{}% in {} trials vs {}.",
                card.glyph,
                card.name,
                card.kind.tag(),
                sign,
                pct,
                SCOUT_GAMES,
                self.bot().name
            ));
        }
    }

    pub fn toggle_focus(&mut self) {
        self.focus = match self.focus {
            Focus::Palette => Focus::Stack,
            Focus::Stack => Focus::Palette,
        };
    }
    fn cursor_step(&mut self, delta: isize) {
        match self.focus {
            Focus::Palette => {
                let n = self.palette.len().max(1);
                self.palette_cursor =
                    (self.palette_cursor as isize + delta).rem_euclid(n as isize) as usize;
            }
            Focus::Stack => {
                let n = self.stack.len().max(1);
                self.stack_cursor =
                    (self.stack_cursor as isize + delta).rem_euclid(n as isize) as usize;
            }
        }
    }
    fn primary_action(&mut self) {
        match self.focus {
            Focus::Palette => {
                if let Some(card) = self.palette.get(self.palette_cursor) {
                    let id = card.id;
                    if !self.is_discovered(id) {
                        self.log_line("That card is still hidden — Scout [s] to unlock it.".into());
                    } else if self.in_stack(id) {
                        self.log_line("Already in your strategy.".into());
                    } else {
                        self.stack.push(id);
                    }
                }
            }
            Focus::Stack => self.remove_from_stack(),
        }
    }
    fn remove_from_stack(&mut self) {
        if self.stack_cursor < self.stack.len() {
            self.stack.remove(self.stack_cursor);
            if self.stack_cursor > 0 && self.stack_cursor >= self.stack.len() {
                self.stack_cursor -= 1;
            }
        }
    }
    fn reorder(&mut self, delta: isize) {
        if self.focus != Focus::Stack {
            return;
        }
        let i = self.stack_cursor;
        let j = i as isize + delta;
        if j >= 0 && (j as usize) < self.stack.len() {
            self.stack.swap(i, j as usize);
            self.stack_cursor = j as usize;
        }
    }
    pub fn cycle_bot(&mut self, delta: isize) {
        let n = self.bots.len() as isize;
        self.selected_bot = ((self.selected_bot as isize + delta).rem_euclid(n)) as usize;
    }

    fn log_line(&mut self, line: String) {
        self.log.push(line);
        if self.log.len() > 200 {
            self.log.remove(0);
        }
    }

    pub fn run_match(&mut self) {
        let you: Vec<String> = self.stack.iter().map(|s| s.to_string()).collect();
        let bot = self.bot().clone();
        let opp: Vec<String> = bot.rule_ids.iter().map(|s| s.to_string()).collect();
        self.match_counter = self.match_counter.wrapping_add(1);
        let base_seed = self
            .base_seed
            .wrapping_add(self.match_counter.wrapping_mul(2_654_435_761));

        let results =
            simulate_match(&self.game, &self.palette, &you, &opp, MATCH_GAMES, base_seed);
        let stats = compute_stats(&results);
        self.log_line(format!(
            "Match vs {}: you {} — {} {} ({} draws).",
            bot.name, stats.you, stats.opp, bot.name, stats.draws
        ));

        if stats.you > stats.opp {
            if !self.beaten.iter().any(|b| *b == bot.key) {
                self.beaten.push(bot.key);
            }
            let mut learned = vec![];
            for id in &bot.rule_ids {
                if self.reveal(id) {
                    learned.push(*id);
                }
            }
            if learned.is_empty() {
                self.log_line(format!("Beat {} — nothing new to learn from them.", bot.name));
            } else {
                self.log_line(format!(
                    "Beat {}! Studied their stack and discovered {} new card(s).",
                    bot.name,
                    learned.len()
                ));
            }
        }

        self.last = Some(MatchView {
            stats,
            results,
            you_ids: you,
            opp_ids: opp,
            base_seed,
            bot_name: bot.name,
            bot_stars: bot.stars,
        });
    }

    // ---- value-function RL ---------------------------------------------- //
    pub fn train_batch(&mut self) {
        self.learner.train(&self.game, EPISODES_PER_BATCH);
        // only the learned values depend on the table; refresh them cheaply
        if !self.terminal() {
            self.learned_vals = self.learner.move_values(&self.game, &self.explore);
            self.explore_learned = self
                .learned_vals
                .iter()
                .map(|(_, v)| *v)
                .fold(f64::NEG_INFINITY, f64::max);
        }
    }
    pub fn toggle_auto(&mut self) {
        self.auto_train = !self.auto_train;
    }
    pub fn reset_learner(&mut self) {
        self.auto_train = false;
        self.learner.reset(&self.game, Rng::new(self.base_seed).below(u32::MAX as usize) as u32);
        self.refresh();
    }
    pub fn table_size(&self) -> usize {
        self.learner.table.len()
    }

    // ---- per-view key handling ------------------------------------------ //
    pub fn on_strategy_key(&mut self, k: KeyCode) {
        match k {
            KeyCode::Tab | KeyCode::Left | KeyCode::Right => self.toggle_focus(),
            KeyCode::Up | KeyCode::Char('k') => self.cursor_step(-1),
            KeyCode::Down | KeyCode::Char('j') => self.cursor_step(1),
            KeyCode::Enter | KeyCode::Char(' ') => self.primary_action(),
            KeyCode::Char('x') | KeyCode::Char('d') | KeyCode::Backspace => {
                self.focus = Focus::Stack;
                self.remove_from_stack();
            }
            KeyCode::Char('[') => self.reorder(-1),
            KeyCode::Char(']') => self.reorder(1),
            KeyCode::Char('s') => self.scout(),
            KeyCode::Char('b') => self.cycle_bot(1),
            KeyCode::Char('B') => self.cycle_bot(-1),
            KeyCode::Char('r') => self.run_match(),
            _ => {}
        }
    }
    pub fn on_value_key(&mut self, k: KeyCode) {
        match k {
            KeyCode::Char('t') => self.train_batch(),
            KeyCode::Char(' ') => self.toggle_auto(),
            KeyCode::Char('R') => self.reset_learner(),
            KeyCode::Up | KeyCode::Char('k') => self.move_cursor_step(-1),
            KeyCode::Down | KeyCode::Char('j') => self.move_cursor_step(1),
            KeyCode::Enter => self.play_selected(),
            KeyCode::Backspace | KeyCode::Char('u') => self.undo(),
            KeyCode::Char('n') => self.reset_explore(),
            _ => {}
        }
    }
    pub fn on_symmetry_key(&mut self, k: KeyCode) {
        match k {
            KeyCode::Up | KeyCode::Char('k') => self.move_cursor_step(-1),
            KeyCode::Down | KeyCode::Char('j') => self.move_cursor_step(1),
            KeyCode::Enter => self.play_selected(),
            KeyCode::Backspace | KeyCode::Char('u') => self.undo(),
            KeyCode::Char('n') => self.reset_explore(),
            _ => {}
        }
    }
}

// --------------------------------------------------------------------------- //
// Replay viewer (non-generic: frames are pre-rendered to sketches)
// --------------------------------------------------------------------------- //
pub struct ReplayFrame {
    pub sketch: BoardSketch,
    pub caption: String,
    pub seat: Option<Seat>,
}
pub struct ReplayView {
    pub frames: Vec<ReplayFrame>,
    pub index: usize,
    pub title: String,
    pub result: String,
}
impl ReplayView {
    pub fn step(&mut self, d: isize) {
        let n = self.frames.len() as isize;
        self.index = (self.index as isize + d).clamp(0, n - 1) as usize;
    }
}

// --------------------------------------------------------------------------- //
// Top-level app
// --------------------------------------------------------------------------- //
pub struct App {
    pub tab: Tab,
    pub active: GameId,
    pub ttt: Session<TicTacToe>,
    pub nim: Session<Nim>,
    pub catan: CatanLab,
    pub show_help: bool,
    pub replay: Option<ReplayView>,
    pub should_quit: bool,
}

/// Run a closure against whichever card-stack session is active (mutable).
/// Catan is *not* a `Session` (it bridges to catanatron), so it must be
/// intercepted before any call here — reaching the Catan arm is a bug.
macro_rules! with_active_mut {
    ($self:ident, $s:ident => $body:expr) => {
        match $self.active {
            GameId::Ttt => {
                let $s = &mut $self.ttt;
                $body
            }
            GameId::Nim => {
                let $s = &mut $self.nim;
                $body
            }
            GameId::Catan => unreachable!("Catan has no Session — route to App::on_catan_key"),
        }
    };
}

impl App {
    pub fn new() -> Self {
        let ttt = Session::new(
            TicTacToe,
            crate::game::tictactoe::cards(),
            crate::game::tictactoe::bots()
                .into_iter()
                .map(|(name, key, stars, desc, rule_ids)| BotPreset { name, key, stars, desc, rule_ids })
                .collect(),
            0xC0FFEE,
        );
        let nim = Session::new(
            Nim,
            crate::game::nim::cards(),
            crate::game::nim::bots()
                .into_iter()
                .map(|(name, key, stars, desc, rule_ids)| BotPreset { name, key, stars, desc, rule_ids })
                .collect(),
            0xBEEF,
        );
        App {
            tab: Tab::Strategy,
            active: GameId::Ttt,
            ttt,
            nim,
            catan: CatanLab::new(),
            show_help: false,
            replay: None,
            should_quit: false,
        }
    }

    pub fn auto_training(&self) -> bool {
        matches!(self.tab, Tab::Value)
            && self.replay.is_none()
            && !self.show_help
            && match self.active {
                GameId::Ttt => self.ttt.auto_train,
                GameId::Nim => self.nim.auto_train,
                GameId::Catan => false, // catanatron drives itself; nothing to auto-train here
            }
    }

    /// Called on a timer tick — advances the learner if auto-training.
    pub fn tick(&mut self) {
        if self.auto_training() {
            with_active_mut!(self, s => s.train_batch());
        }
    }

    pub fn on_key(&mut self, k: KeyCode) {
        // Overlays grab input first.
        if self.show_help {
            if matches!(k, KeyCode::Esc | KeyCode::Char('?') | KeyCode::Char('q')) {
                self.show_help = false;
            }
            return;
        }
        if self.replay.is_some() {
            self.replay_key(k);
            return;
        }

        match k {
            KeyCode::Char('q') => self.should_quit = true,
            KeyCode::Esc => self.should_quit = true,
            KeyCode::Char('?') => self.show_help = true,
            KeyCode::Char('1') => self.tab = Tab::Strategy,
            KeyCode::Char('2') => self.tab = Tab::Value,
            KeyCode::Char('3') => self.tab = Tab::Symmetry,
            KeyCode::Char('g') => self.switch_game(),
            KeyCode::Char('v')
                if matches!(self.tab, Tab::Strategy) && self.active != GameId::Catan =>
            {
                self.open_replay()
            }
            _ if self.active == GameId::Catan => self.on_catan_key(k),
            _ => match self.tab {
                Tab::Strategy => with_active_mut!(self, s => s.on_strategy_key(k)),
                Tab::Value => with_active_mut!(self, s => s.on_value_key(k)),
                Tab::Symmetry => with_active_mut!(self, s => s.on_symmetry_key(k)),
            },
        }
    }

    fn switch_game(&mut self) {
        self.active = match self.active {
            GameId::Ttt => GameId::Nim,
            GameId::Nim => GameId::Catan,
            GameId::Catan => GameId::Ttt,
        };
    }

    /// Catan key handling. The three tabs become: 1 Tuner & Simulate,
    /// 2 Step-through play, 3 About. All engine calls go through `self.catan`.
    fn on_catan_key(&mut self, k: KeyCode) {
        let lab = &mut self.catan;
        // `d` (sync with engine) works from any Catan tab.
        if matches!(k, KeyCode::Char('d')) {
            lab.sync_defaults();
            return;
        }
        match self.tab {
            Tab::Strategy => match k {
                KeyCode::Up | KeyCode::Char('k') => lab.cursor_step(-1),
                KeyCode::Down | KeyCode::Char('j') => lab.cursor_step(1),
                KeyCode::Left | KeyCode::Char('h') => lab.adjust_selected(-1.0),
                KeyCode::Right | KeyCode::Char('l') => lab.adjust_selected(1.0),
                KeyCode::Char('o') => lab.cycle_opponent(1),
                KeyCode::Char('O') => lab.cycle_opponent(-1),
                KeyCode::Char('T') => lab.toggle_trade(),
                KeyCode::Char('[') => lab.adjust_sim_n(-5),
                KeyCode::Char(']') => lab.adjust_sim_n(5),
                KeyCode::Char('r') | KeyCode::Enter => lab.simulate(),
                KeyCode::Char('R') => lab.reset_defaults(),
                _ => {}
            },
            Tab::Value => match k {
                KeyCode::Char('n') => lab.new_game(),
                KeyCode::Char('t') | KeyCode::Char(' ') | KeyCode::Enter => lab.tick(),
                KeyCode::Char('f') => lab.fast_forward(10),
                KeyCode::Char('o') => lab.cycle_opponent(1),
                KeyCode::Char('O') => lab.cycle_opponent(-1),
                _ => {}
            },
            Tab::Symmetry => {}
        }
    }

    fn replay_key(&mut self, k: KeyCode) {
        let Some(r) = self.replay.as_mut() else { return };
        match k {
            KeyCode::Esc | KeyCode::Char('v') | KeyCode::Char('q') => self.replay = None,
            KeyCode::Left => r.step(-1),
            KeyCode::Right => r.step(1),
            KeyCode::Home => r.index = 0,
            KeyCode::End => r.index = r.frames.len().saturating_sub(1),
            _ => {}
        }
    }

    /// Build a replay of the most interesting recent game (first you-win, else
    /// the longest game) for the active session.
    fn open_replay(&mut self) {
        let view = match self.active {
            GameId::Ttt => build_replay(&self.ttt),
            GameId::Nim => build_replay(&self.nim),
            GameId::Catan => None, // catanatron has its own step-through view
        };
        self.replay = view;
    }
}

fn build_replay<G: Game>(s: &Session<G>) -> Option<ReplayView> {
    let last = s.last.as_ref()?;
    let idx = last
        .stats
        .first_you_win
        .or(last.stats.longest_game)
        .or(last.stats.first_draw)
        .or(last.stats.first_opp_win)
        .unwrap_or(0);
    let outcome = replay_game(
        &s.game,
        &s.palette,
        &last.you_ids,
        &last.opp_ids,
        idx,
        last.base_seed,
    );
    let frames = outcome
        .frames?
        .iter()
        .map(|f| ReplayFrame {
            sketch: s.game.sketch(&f.state),
            caption: f.caption.clone(),
            seat: f.seat,
        })
        .collect();
    let result = match outcome.winner {
        Some(YOU) => "you won this one".to_string(),
        Some(_) => format!("{} won this one", last.bot_name),
        None => "a draw".to_string(),
    };
    Some(ReplayView {
        frames,
        index: 0,
        title: format!("Game {} of {} — replay", idx + 1, MATCH_GAMES),
        result,
    })
}

impl Default for App {
    fn default() -> Self {
        Self::new()
    }
}

// A couple of accessors the UI uses without caring which game is active.
impl App {
    pub fn card_kind_tag(kind: CardKind) -> &'static str {
        kind.tag()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const PERFECT: [&str; 8] = [
        "win", "block", "fork", "block-fork", "center", "opp-corner", "corner", "edge",
    ];

    #[test]
    fn scout_discovers_a_card() {
        let mut app = App::new();
        let before = app.ttt.discovered_count();
        app.ttt.scout();
        assert_eq!(app.ttt.discovered_count(), before + 1, "scout reveals one card");
    }

    #[test]
    fn scouting_everything_then_stops() {
        let mut app = App::new();
        for _ in 0..app.ttt.palette.len() + 3 {
            app.ttt.scout();
        }
        assert_eq!(
            app.ttt.discovered_count(),
            app.ttt.palette.len(),
            "discovery saturates at the full palette and never over-counts"
        );
    }

    #[test]
    fn match_totals_exactly_100() {
        let mut app = App::new();
        app.ttt.scout();
        app.ttt.run_match();
        let m = app.ttt.last.as_ref().expect("a match was recorded");
        assert_eq!(m.stats.you + m.stats.opp + m.stats.draws, 100);
        assert_eq!(m.stats.momentum.len(), 101);
    }

    #[test]
    fn beating_a_bot_marks_it_and_steals_its_cards() {
        let mut app = App::new();
        app.ttt.stack = PERFECT.to_vec(); // a provably perfect policy
        app.ttt.selected_bot = 2; // Careful Carla (win + block, no forks)
        assert!(!app.ttt.is_discovered("block") || true);
        app.ttt.run_match();
        let st = &app.ttt.last.as_ref().unwrap().stats;
        assert!(st.you > st.opp, "perfect must beat a fork-blind bot");
        assert_eq!(st.opp, 0, "perfect never loses");
        assert!(app.ttt.beaten.iter().any(|b| *b == "careful"), "bot recorded as beaten");
        assert!(app.ttt.is_discovered("block"), "studying the beaten bot revealed its cards");
    }

    #[test]
    fn training_advances_and_reduces_error() {
        let mut app = App::new();
        let m0 = app.ttt.learner.latest();
        for _ in 0..6 {
            app.ttt.train_batch();
        }
        let m1 = app.ttt.learner.latest();
        assert!(m1.episodes > m0.episodes, "episodes advance");
        assert!(m1.mae < m0.mae, "error to optimal shrinks: {} -> {}", m0.mae, m1.mae);
    }

    #[test]
    fn explore_play_undo_reset_roundtrip() {
        let mut app = App::new();
        let opening = app.ttt.legal().len();
        assert_eq!(opening, 9);
        app.ttt.on_symmetry_key(KeyCode::Enter); // play the selected move
        assert_eq!(app.ttt.legal().len(), 8, "a move was played");
        app.ttt.on_symmetry_key(KeyCode::Char('u')); // undo
        assert_eq!(app.ttt.legal().len(), 9, "undo restores the board");
        app.ttt.on_symmetry_key(KeyCode::Enter);
        app.ttt.on_symmetry_key(KeyCode::Enter);
        app.ttt.on_symmetry_key(KeyCode::Char('n')); // new board
        assert_eq!(app.ttt.legal().len(), 9, "reset returns to the start");
        assert!(app.ttt.trail.is_empty());
    }

    #[test]
    fn opening_collapses_to_three_core_decisions() {
        let app = App::new();
        assert_eq!(app.ttt.classes.len(), 3, "corner / edge / center");
        let total: usize = app.ttt.classes.iter().map(|c| c.size).sum();
        assert_eq!(total, 9, "the three classes cover all nine moves");
        assert!(app.ttt.classes.iter().any(|c| c.is_optimal));
    }

    #[test]
    fn nim_explore_values_match_solver() {
        // From the start a winning move exists, so the best move value is +1.
        let app = App::new();
        let best = app
            .nim
            .exact_vals
            .iter()
            .map(|(_, v)| *v)
            .fold(f64::NEG_INFINITY, f64::max);
        assert_eq!(best, 1.0, "Nim 3-4-5 is a first-player win");
    }

    #[test]
    fn global_keys_switch_game_tab_help_quit() {
        let mut app = App::new();
        assert!(matches!(app.active, GameId::Ttt));
        app.on_key(KeyCode::Char('g'));
        assert!(matches!(app.active, GameId::Nim));
        app.on_key(KeyCode::Char('2'));
        assert!(matches!(app.tab, Tab::Value));
        app.on_key(KeyCode::Char('?'));
        assert!(app.show_help);
        app.on_key(KeyCode::Esc); // closes help, does not quit
        assert!(!app.show_help && !app.should_quit);
        app.on_key(KeyCode::Char('q'));
        assert!(app.should_quit);
    }

    #[test]
    fn replay_builds_frames_from_last_match() {
        let mut app = App::new();
        app.ttt.scout();
        app.ttt.run_match();
        app.open_replay();
        let r = app.replay.as_ref().expect("a replay opened");
        assert!(r.frames.len() >= 2, "replay has a start frame and at least one move");
        assert!(!r.result.is_empty());
        // stepping is clamped to bounds
        app.replay.as_mut().unwrap().step(-5);
        assert_eq!(app.replay.as_ref().unwrap().index, 0);
    }

    #[test]
    fn auto_training_only_in_value_tab() {
        let mut app = App::new();
        app.ttt.auto_train = true;
        app.tab = Tab::Strategy;
        assert!(!app.auto_training(), "auto-train is gated to the value tab");
        app.tab = Tab::Value;
        assert!(app.auto_training());
        let before = app.ttt.learner.latest().episodes;
        app.tick();
        assert!(app.ttt.learner.latest().episodes > before, "tick trains while auto on");
    }
}
