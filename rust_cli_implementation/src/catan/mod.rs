//! The Catan lens — a *bridge*, not a reimplementation.
//!
//! Unlike Tic-Tac-Toe and Nim (which are tiny, solved, and implement the `Game`
//! trait so all three lenses apply), Settlers of Catan is far too large to solve,
//! has dice and four seats, and so cannot be a `Game` here. Instead this module
//! mirrors `strategy-lab`'s **Catan Lab**: the *real* catanatron engine computes
//! every rule, move and tick behind a small HTTP API, and we design the *policy*
//! — a position-strength metric plus a non-linear trade coefficient — and watch
//! it play.
//!
//! Everything in this file is UI-agnostic: it owns the tuner state, talks to the
//! engine through [`client::CatanClient`], and parses results into plain structs
//! the terminal layer renders. The server is `catan-server/app.py` (started with
//! `./scripts/catan-server.sh`); when it isn't running, every action degrades to
//! a status message instead of doing anything dangerous.

mod client;

pub use client::CatanClient;
use serde_json::{json, Value};

/// One tunable knob in the policy, mapped 1:1 to a server-side JSON field.
#[derive(Clone)]
pub struct Param {
    pub key: &'static str,
    pub label: &'static str,
    pub help: &'static str,
    pub value: f64,
    pub min: f64,
    pub max: f64,
    pub step: f64,
    pub is_int: bool,
}

impl Param {
    fn adjust(&mut self, dir: f64) {
        let v = self.value + dir * self.step;
        self.value = v.clamp(self.min, self.max);
        if self.is_int {
            self.value = self.value.round();
        }
    }
    pub fn display(&self) -> String {
        if self.is_int {
            format!("{}", self.value.round() as i64)
        } else {
            format!("{:.2}", self.value)
        }
    }
    /// Position of the value within [min, max], for a slider bar.
    pub fn frac(&self) -> f64 {
        if self.max <= self.min {
            0.0
        } else {
            ((self.value - self.min) / (self.max - self.min)).clamp(0.0, 1.0)
        }
    }
}

/// Aggregated outcome of a batch simulation (`/api/simulate`).
#[derive(Clone)]
pub struct SimResult {
    pub games: usize,
    pub opponent: String,
    pub you_wins: usize,
    pub opp_wins: usize,
    pub draws: usize,
    pub winrate: f64,
    pub avg_turns: f64,
    pub avg_your_vp: f64,
    pub avg_opp_vp: f64,
    // trade tally
    pub offers: u64,
    pub accepts: u64,
    pub rejects: u64,
    pub confirms: u64,
    pub cancels: u64,
    pub vetoes: u64,
}

/// One tile of the catanatron board (resource + dice number).
#[derive(Clone)]
pub struct Tile {
    pub resource: Option<String>,
    pub number: Option<u64>,
}

/// A player's public situation, as the server serializes it.
#[derive(Clone)]
pub struct PlayerInfo {
    pub color: String,
    pub is_you: bool,
    pub vp: u64,
    pub public_vp: u64,
    pub hand: [u64; 5],
    pub dev_cards: u64,
    pub longest_road: u64,
    pub strength: f64,
}

/// A parsed snapshot of the live game state.
#[derive(Clone)]
pub struct CatanState {
    pub tiles: Vec<Tile>,
    pub robber_tile: Option<usize>,
    pub num_buildings: usize,
    pub num_roads: usize,
    pub players: Vec<PlayerInfo>,
    pub current_color: String,
    pub prompt: String,
    pub num_turns: u64,
    pub winner: Option<String>,
}

/// A step-through game in progress on the server.
pub struct StepGame {
    pub game_id: String,
    pub seed: i64,
    pub state: CatanState,
    pub last_actor: Option<String>,
    pub last_action: Option<String>,
    pub last_explanation: Option<String>,
    pub log: Vec<String>,
    pub done: bool,
}

/// Hand / resource labels in catanatron's freqdeck order.
pub const RESOURCES: [&str; 5] = ["wood", "brick", "sheep", "wheat", "ore"];

pub struct CatanLab {
    pub client: CatanClient,
    pub weights: Vec<Param>,
    pub trade: Vec<Param>,
    pub cursor: usize, // across weights then trade
    pub opponents: Vec<String>,
    pub opponent: usize,
    pub enable_trade: bool,
    pub sim_n: usize,
    pub status: String,
    pub last_sim: Option<SimResult>,
    pub game: Option<StepGame>,
    /// Set once we've successfully reached the server at least once.
    pub server_seen: bool,
}

impl Default for CatanLab {
    fn default() -> Self {
        Self::new()
    }
}

impl CatanLab {
    pub fn new() -> Self {
        let mut lab = CatanLab {
            client: CatanClient::default(),
            weights: default_weights(),
            trade: default_trade(),
            cursor: 0,
            opponents: vec![
                "RANDOM".into(),
                "WEIGHTED".into(),
                "VALUE".into(),
                "ALPHABETA".into(),
                "TRADER".into(),
            ],
            opponent: 2, // VALUE — the engine's own value-function bot
            enable_trade: true,
            sim_n: 20,
            status: format!(
                "Start the engine:  ./scripts/catan-server.sh   ({}). Then [d] sync · [r] simulate · [n] new game.",
                CatanClient::default().base()
            ),
            last_sim: None,
            game: None,
            server_seen: false,
        };
        // A best-effort, fast-failing handshake so a running server populates
        // live opponent list / ranges immediately; offline just leaves the hint.
        lab.sync_defaults_quiet();
        lab
    }

    // ---- params --------------------------------------------------------- //
    pub fn params_len(&self) -> usize {
        self.weights.len() + self.trade.len()
    }
    /// `(is_trade_group, index_within_group)` for the global cursor.
    fn locate(&self, cursor: usize) -> (bool, usize) {
        if cursor < self.weights.len() {
            (false, cursor)
        } else {
            (true, cursor - self.weights.len())
        }
    }
    pub fn param_at(&self, cursor: usize) -> &Param {
        let (trade, i) = self.locate(cursor);
        if trade {
            &self.trade[i]
        } else {
            &self.weights[i]
        }
    }
    pub fn cursor_step(&mut self, delta: isize) {
        let n = self.params_len() as isize;
        if n == 0 {
            return;
        }
        self.cursor = (self.cursor as isize + delta).rem_euclid(n) as usize;
    }
    pub fn adjust_selected(&mut self, dir: f64) {
        let (trade, i) = self.locate(self.cursor);
        if trade {
            self.trade[i].adjust(dir);
        } else {
            self.weights[i].adjust(dir);
        }
    }
    pub fn reset_defaults(&mut self) {
        self.weights = default_weights();
        self.trade = default_trade();
        self.status = "Reset weights & trade params to catanatron defaults.".into();
    }
    pub fn cycle_opponent(&mut self, delta: isize) {
        let n = self.opponents.len() as isize;
        if n > 0 {
            self.opponent = (self.opponent as isize + delta).rem_euclid(n) as usize;
        }
    }
    pub fn toggle_trade(&mut self) {
        self.enable_trade = !self.enable_trade;
    }
    pub fn adjust_sim_n(&mut self, delta: isize) {
        let v = self.sim_n as isize + delta;
        self.sim_n = v.clamp(1, 300) as usize;
    }
    pub fn opponent_name(&self) -> &str {
        self.opponents
            .get(self.opponent)
            .map(|s| s.as_str())
            .unwrap_or("VALUE")
    }

    fn weights_json(&self) -> Value {
        let mut m = serde_json::Map::new();
        for p in &self.weights {
            m.insert(p.key.to_string(), json!(p.value));
        }
        Value::Object(m)
    }
    fn trade_json(&self) -> Value {
        let mut m = serde_json::Map::new();
        for p in &self.trade {
            let v = if p.is_int {
                json!(p.value.round() as i64)
            } else {
                json!(p.value)
            };
            m.insert(p.key.to_string(), v);
        }
        Value::Object(m)
    }

    // ---- server calls --------------------------------------------------- //
    /// Pull live ranges / opponent list. Quiet variant for construction.
    fn sync_defaults_quiet(&mut self) {
        if let Ok(v) = self.client.get("/api/defaults") {
            self.apply_defaults(&v);
            self.server_seen = true;
        }
    }

    /// Explicit "sync with engine" action (the `d` key).
    pub fn sync_defaults(&mut self) {
        match self.client.get("/api/defaults") {
            Ok(v) => {
                self.apply_defaults(&v);
                self.server_seen = true;
                self.status = format!("Connected to catanatron at {}.", self.client.base());
            }
            Err(e) => self.status = format!("{e}"),
        }
    }

    fn apply_defaults(&mut self, v: &Value) {
        if let Some(opps) = v.get("opponents").and_then(|o| o.as_array()) {
            let list: Vec<String> = opps
                .iter()
                .filter_map(|s| s.as_str().map(String::from))
                .collect();
            if !list.is_empty() {
                let cur = self.opponent_name().to_string();
                self.opponents = list;
                self.opponent = self
                    .opponents
                    .iter()
                    .position(|o| *o == cur)
                    .unwrap_or(self.opponent.min(self.opponents.len() - 1));
            }
        }
        // Tighten our slider ranges to whatever the server advertises.
        if let Some(ranges) = v.get("ranges").and_then(|r| r.as_object()) {
            for p in self.weights.iter_mut().chain(self.trade.iter_mut()) {
                if let Some(arr) = ranges.get(p.key).and_then(|a| a.as_array()) {
                    if arr.len() == 2 {
                        if let (Some(lo), Some(hi)) = (arr[0].as_f64(), arr[1].as_f64()) {
                            p.min = lo;
                            p.max = hi;
                            p.value = p.value.clamp(lo, hi);
                        }
                    }
                }
            }
        }
    }

    /// Run a batch simulation with the current policy (the `r` key).
    pub fn simulate(&mut self) {
        let body = json!({
            "n": self.sim_n,
            "seed": 0,
            "opponent": self.opponent_name(),
            "enable_trade": self.enable_trade,
            "weights": self.weights_json(),
            "trade": self.trade_json(),
        });
        self.status = format!(
            "Simulating {} games vs {}…",
            self.sim_n,
            self.opponent_name()
        );
        match self.client.post("/api/simulate", &body) {
            Ok(v) => {
                self.server_seen = true;
                self.last_sim = Some(parse_sim(&v));
                let r = self.last_sim.as_ref().unwrap();
                self.status = format!(
                    "Done: {} of {} wins ({:.0}%) vs {}.",
                    r.you_wins,
                    r.games,
                    r.winrate * 100.0,
                    r.opponent
                );
            }
            Err(e) => self.status = format!("{e}"),
        }
    }

    /// Start a fresh step-through game (the `n` key).
    pub fn new_game(&mut self) {
        let body = json!({
            "opponent": self.opponent_name(),
            "enable_trade": self.enable_trade,
            "weights": self.weights_json(),
            "trade": self.trade_json(),
        });
        match self.client.post("/api/game", &body) {
            Ok(v) => {
                self.server_seen = true;
                let game_id = v
                    .get("game_id")
                    .and_then(|g| g.as_str())
                    .unwrap_or("")
                    .to_string();
                let seed = v.get("seed").and_then(|s| s.as_i64()).unwrap_or(0);
                let state = parse_state(v.get("state").unwrap_or(&Value::Null));
                self.game = Some(StepGame {
                    game_id,
                    seed,
                    state,
                    last_actor: None,
                    last_action: None,
                    last_explanation: None,
                    log: vec![format!("New game (seed {seed}) vs {}.", self.opponent_name())],
                    done: false,
                });
                self.status = format!("New game vs {}. [t] tick · [f] fast-forward 10.", self.opponent_name());
            }
            Err(e) => self.status = format!("{e}"),
        }
    }

    /// Advance the live game by one ply (the `t` key).
    pub fn tick(&mut self) {
        let Some(gid) = self.game.as_ref().map(|g| g.game_id.clone()) else {
            self.status = "No game yet — press [n] to start one.".into();
            return;
        };
        if self.game.as_ref().map(|g| g.done).unwrap_or(true) {
            self.status = "Game is over — [n] starts a new one.".into();
            return;
        }
        match self.client.post(&format!("/api/game/{gid}/tick"), &json!({})) {
            Ok(v) => {
                self.server_seen = true;
                let done = v.get("done").and_then(|d| d.as_bool()).unwrap_or(false);
                let actor = v.get("actor").and_then(|a| a.as_str()).map(String::from);
                let action = v.get("action").map(format_action);
                let explanation = v.get("explanation").map(format_explanation);
                let state = parse_state(v.get("state").unwrap_or(&Value::Null));
                if let Some(g) = self.game.as_mut() {
                    let line = format!(
                        "{} · {}",
                        actor.clone().unwrap_or_else(|| "?".into()),
                        action.clone().unwrap_or_else(|| "—".into())
                    );
                    g.log.push(line);
                    if g.log.len() > 200 {
                        g.log.remove(0);
                    }
                    g.last_actor = actor;
                    g.last_action = action;
                    g.last_explanation = explanation;
                    g.state = state;
                    g.done = done;
                    if done {
                        let w = g
                            .state
                            .winner
                            .clone()
                            .unwrap_or_else(|| "nobody".into());
                        self.status = format!("Game over — {w} wins.");
                    }
                }
            }
            Err(e) => self.status = format!("{e}"),
        }
    }

    /// Tick repeatedly (the `f` key); stops early if the game ends or errors.
    pub fn fast_forward(&mut self, plies: usize) {
        for _ in 0..plies {
            if self.game.as_ref().map(|g| g.done).unwrap_or(true) {
                break;
            }
            let before = self.game.as_ref().map(|g| g.log.len()).unwrap_or(0);
            self.tick();
            // tick() only appends to the log on success; bail on a stall/error.
            if self.game.as_ref().map(|g| g.log.len()).unwrap_or(0) == before {
                break;
            }
        }
    }
}

// --------------------------------------------------------------------------- //
// Parsing helpers
// --------------------------------------------------------------------------- //
fn parse_sim(v: &Value) -> SimResult {
    let t = v.get("trades").cloned().unwrap_or(Value::Null);
    let g = |k: &str| t.get(k).and_then(|x| x.as_u64()).unwrap_or(0);
    SimResult {
        games: v.get("games").and_then(|x| x.as_u64()).unwrap_or(0) as usize,
        opponent: v
            .get("opponent")
            .and_then(|x| x.as_str())
            .unwrap_or("?")
            .to_string(),
        you_wins: v.get("you_wins").and_then(|x| x.as_u64()).unwrap_or(0) as usize,
        opp_wins: v.get("opp_wins").and_then(|x| x.as_u64()).unwrap_or(0) as usize,
        draws: v.get("draws").and_then(|x| x.as_u64()).unwrap_or(0) as usize,
        winrate: v.get("you_winrate").and_then(|x| x.as_f64()).unwrap_or(0.0),
        avg_turns: v.get("avg_turns").and_then(|x| x.as_f64()).unwrap_or(0.0),
        avg_your_vp: v.get("avg_your_vp").and_then(|x| x.as_f64()).unwrap_or(0.0),
        avg_opp_vp: v.get("avg_opp_vp").and_then(|x| x.as_f64()).unwrap_or(0.0),
        offers: g("offers"),
        accepts: g("accepts"),
        rejects: g("rejects"),
        confirms: g("confirms"),
        cancels: g("cancels"),
        vetoes: g("vetoes"),
    }
}

fn parse_state(v: &Value) -> CatanState {
    let tiles = v
        .get("tiles")
        .and_then(|t| t.as_array())
        .map(|arr| {
            arr.iter()
                .map(|t| Tile {
                    resource: t.get("resource").and_then(|r| r.as_str()).map(String::from),
                    number: t.get("number").and_then(|n| n.as_u64()),
                })
                .collect()
        })
        .unwrap_or_default();

    let players = v
        .get("players")
        .and_then(|p| p.as_array())
        .map(|arr| arr.iter().map(parse_player).collect())
        .unwrap_or_default();

    let num_buildings = v
        .get("buildings")
        .and_then(|b| b.as_object())
        .map(|o| o.len())
        .unwrap_or(0);
    let num_roads = v
        .get("roads")
        .and_then(|r| r.as_array())
        .map(|a| a.len())
        .unwrap_or(0);

    CatanState {
        tiles,
        robber_tile: v.get("robber_tile").and_then(|r| r.as_u64()).map(|n| n as usize),
        num_buildings,
        num_roads,
        players,
        current_color: v
            .get("current_color")
            .and_then(|c| c.as_str())
            .unwrap_or("?")
            .to_string(),
        prompt: v
            .get("prompt")
            .and_then(|c| c.as_str())
            .unwrap_or("")
            .to_string(),
        num_turns: v.get("num_turns").and_then(|c| c.as_u64()).unwrap_or(0),
        winner: v.get("winner").and_then(|w| w.as_str()).map(String::from),
    }
}

fn parse_player(v: &Value) -> PlayerInfo {
    let mut hand = [0u64; 5];
    if let Some(arr) = v.get("hand").and_then(|h| h.as_array()) {
        for (i, x) in arr.iter().take(5).enumerate() {
            hand[i] = x.as_u64().unwrap_or(0);
        }
    }
    PlayerInfo {
        color: v.get("color").and_then(|c| c.as_str()).unwrap_or("?").to_string(),
        is_you: v.get("is_you").and_then(|b| b.as_bool()).unwrap_or(false),
        vp: v.get("vp").and_then(|x| x.as_u64()).unwrap_or(0),
        public_vp: v.get("public_vp").and_then(|x| x.as_u64()).unwrap_or(0),
        hand,
        dev_cards: v.get("dev_cards").and_then(|x| x.as_u64()).unwrap_or(0),
        longest_road: v.get("longest_road").and_then(|x| x.as_u64()).unwrap_or(0),
        strength: v.get("strength").and_then(|x| x.as_f64()).unwrap_or(0.0),
    }
}

fn format_action(v: &Value) -> String {
    let by = v.get("by").and_then(|b| b.as_str()).unwrap_or("?");
    let ty = v.get("type").and_then(|t| t.as_str()).unwrap_or("?");
    let val = v.get("value");
    match val {
        Some(Value::Null) | None => format!("{by}: {}", pretty(ty)),
        Some(x) => format!("{by}: {} {}", pretty(ty), compact_value(x)),
    }
}

fn pretty(ty: &str) -> String {
    let mut s = ty.to_lowercase().replace('_', " ");
    if let Some(c) = s.get_mut(0..1) {
        c.make_ascii_uppercase();
    }
    s
}

fn compact_value(v: &Value) -> String {
    match v {
        Value::Array(a) => {
            let parts: Vec<String> = a.iter().map(compact_value).collect();
            format!("[{}]", parts.join(","))
        }
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Null => "·".into(),
        other => other.to_string(),
    }
}

/// Render the policy's reasoning dict into one readable line.
fn format_explanation(v: &Value) -> String {
    let kind = v.get("kind").and_then(|k| k.as_str()).unwrap_or("");
    let note = v.get("note").and_then(|n| n.as_str()).unwrap_or("");
    let mut out = match (kind, note) {
        ("", "") => "—".to_string(),
        (k, "") => format!("[{k}]"),
        ("", n) => n.to_string(),
        (k, n) => format!("[{k}] {n}"),
    };
    // Trade reasoning carries the numbers that make this lab interesting.
    if let Some(r) = v.get("reasoning") {
        let g = |key: &str| r.get(key).and_then(|x| x.as_f64());
        if let (Some(lam), Some(net)) = (g("lambda"), g("net")) {
            out.push_str(&format!(
                "  ·  λ={lam:.2} net={net:+.2} mine={:+.2} theirs={:+.2} req={:.2}",
                g("my_gain").unwrap_or(0.0),
                g("their_gain").unwrap_or(0.0),
                g("required").unwrap_or(0.0),
            ));
            if r.get("vetoed").and_then(|x| x.as_bool()).unwrap_or(false) {
                out.push_str("  ·  VETO (opp near win)");
            }
        }
    }
    out
}

// --------------------------------------------------------------------------- //
// Defaults — mirror policy.py MetricWeights / TradeParams; refined live by
// /api/defaults when the server is reachable.
// --------------------------------------------------------------------------- //
fn default_weights() -> Vec<Param> {
    vec![
        p("vp", "VP weight", "closeness-to-victory share of strength", 0.6, 0.0, 1.0, 0.05, false),
        p("production", "Production", "pip-economy share of strength", 0.25, 0.0, 1.0, 0.05, false),
        p("expansion", "Expansion", "buildable-reach share of strength", 0.15, 0.0, 1.0, 0.05, false),
        p("prod_norm", "Prod norm", "pips that count as a 'full' economy", 12.0, 4.0, 24.0, 1.0, false),
        p("expansion_norm", "Exp norm", "nodes that count as 'full' reach", 8.0, 2.0, 16.0, 1.0, false),
    ]
}

fn default_trade() -> Vec<Param> {
    vec![
        p("lam_max", "λ max", "ceiling of the trade coefficient", 2.5, 0.0, 5.0, 0.1, false),
        p("lam_steepness", "λ steepness", "how sharply λ turns on", 8.0, 1.0, 20.0, 0.5, false),
        p("lam_midpoint", "λ midpoint", "opp strength where λ = max/2", 0.5, 0.0, 1.0, 0.05, false),
        p("veto_vp_margin", "Veto margin", "never trade if opp within N VP of win", 1.0, 0.0, 4.0, 1.0, true),
        p("margin", "Min margin", "min net value to bother trading", 0.15, 0.0, 2.0, 0.05, false),
        p("premium_per_vp", "Premium/VP", "extra demanded per VP the opp leads", 0.5, 0.0, 2.0, 0.05, false),
        p("scarcity_weight", "Scarcity", "value of a resource you barely make", 1.0, 0.0, 3.0, 0.1, false),
        p("need_weight", "Need", "value of a resource that completes a build", 1.5, 0.0, 4.0, 0.1, false),
        p("base_value", "Base value", "floor value of any resource", 0.5, 0.0, 2.0, 0.05, false),
    ]
}

#[allow(clippy::too_many_arguments)]
fn p(
    key: &'static str,
    label: &'static str,
    help: &'static str,
    value: f64,
    min: f64,
    max: f64,
    step: f64,
    is_int: bool,
) -> Param {
    Param { key, label, help, value, min, max, step, is_int }
}

/// The logistic trade coefficient λ(opp_strength), mirrored from policy.py so the
/// UI can draw the curve without a round-trip.
pub fn lambda_curve(trade: &[Param], opp_strength: f64) -> f64 {
    let get = |k: &str| trade.iter().find(|p| p.key == k).map(|p| p.value);
    let lam_max = get("lam_max").unwrap_or(2.5);
    let steep = get("lam_steepness").unwrap_or(8.0);
    let mid = get("lam_midpoint").unwrap_or(0.5);
    let z = steep * (opp_strength - mid);
    lam_max / (1.0 + (-z).exp())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cursor_wraps_across_both_groups() {
        let mut lab = CatanLab::new();
        let n = lab.params_len();
        assert_eq!(n, lab.weights.len() + lab.trade.len());
        lab.cursor = n - 1;
        lab.cursor_step(1);
        assert_eq!(lab.cursor, 0, "wraps to the first param");
        lab.cursor_step(-1);
        assert_eq!(lab.cursor, n - 1, "wraps back to the last");
    }

    #[test]
    fn adjust_is_clamped_and_int_aware() {
        let mut lab = CatanLab::new();
        // veto_vp_margin is the integer param; drive it past its max.
        let idx = lab.weights.len()
            + lab.trade.iter().position(|p| p.key == "veto_vp_margin").unwrap();
        lab.cursor = idx;
        for _ in 0..20 {
            lab.adjust_selected(1.0);
        }
        let p = lab.param_at(idx);
        assert_eq!(p.value, p.max);
        assert_eq!(p.value, p.value.round(), "integer param stays whole");
    }

    #[test]
    fn lambda_is_logistic_and_rises_with_strength() {
        let trade = default_trade();
        let weak = lambda_curve(&trade, 0.0);
        let mid = lambda_curve(&trade, 0.5);
        let strong = lambda_curve(&trade, 1.0);
        assert!(weak < mid && mid < strong, "λ rises with opponent strength");
        assert!((mid - 2.5 / 2.0).abs() < 1e-6, "λ(midpoint) = max/2");
    }

    #[test]
    fn json_round_trips_every_param_key() {
        let lab = CatanLab::new();
        let w = lab.weights_json();
        for p in &lab.weights {
            assert!(w.get(p.key).is_some(), "weight {} serialized", p.key);
        }
        let t = lab.trade_json();
        for p in &lab.trade {
            assert!(t.get(p.key).is_some(), "trade {} serialized", p.key);
        }
        // the integer param must serialize as an integer, not 1.0
        assert!(t.get("veto_vp_margin").unwrap().is_i64());
    }

    #[test]
    fn explanation_formats_trade_reasoning() {
        let v = json!({
            "kind": "respond", "note": "accept",
            "reasoning": {"lambda": 1.2, "net": 0.4, "my_gain": 0.6,
                          "their_gain": 0.2, "required": 0.15, "vetoed": false}
        });
        let s = format_explanation(&v);
        assert!(s.contains("[respond] accept"));
        assert!(s.contains("λ=1.20") && s.contains("net=+0.40"));
    }
}
