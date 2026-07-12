/* ============================================================
 * Strategy Lab — UI layer.
 * Three views: home (game gallery) → lab (build a strategy)
 * → results (100-game match statistics + replays).
 * ============================================================ */
window.UI = (function () {
  'use strict';

  const NGAMES = 100;
  const STORE_KEY = 'strategy-lab-v1';

  const COMING_SOON = [
    { icon: '🛞', name: 'The Game of Life', blurb: 'Careers, kids and a big spinner of destiny.', genre: 'classic' },
    { icon: '🎲', name: 'Backgammon', blurb: 'The oldest race game in the world.', genre: 'board' },
  ];

  let stacks = {};   // gameId -> [ruleId]
  let bots = {};     // gameId -> presetId
  let beaten = {};   // gameId -> { presetId: true }
  let game = null;   // game currently open in the lab
  let last = null;   // last match data
  let dragIndex = null;

  const root = () => document.getElementById('app');
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));

  /* ---------- persistence ---------- */
  function loadStore() {
    try {
      const d = JSON.parse(localStorage.getItem(STORE_KEY)) || {};
      stacks = d.stacks || {};
      bots = d.bots || {};
      beaten = d.beaten || {};
    } catch (e) { stacks = {}; bots = {}; beaten = {}; }
  }
  function saveStore() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ stacks, bots, beaten }));
    } catch (e) { /* private mode etc. — non-fatal */ }
  }

  function userIdsFor(g) { return stacks[g.id] || (stacks[g.id] = []); }
  function presetFor(g) {
    const id = bots[g.id];
    return g.botPresets.find(p => p.id === id) || g.botPresets[0];
  }
  function stars(n) { return '★'.repeat(n) + '<i>' + '★'.repeat(4 - n) + '</i>'; }
  function badge(kind) {
    return `<span class="badge ${kind}">${kind === 'avoid' ? 'AVOID' : 'PICK'}</span>`;
  }

  /* ============================= HOME ============================= */
  let genreFilter = 'all';
  let gymLive = null;           // cached /api/gym/envs payload (or 'offline')

  function showHome() {
    game = null;
    const entries = [];         // { genre, html }

    StrategyLab.games.forEach(g => {
      const won = Object.keys(beaten[g.id] || {}).length;
      entries.push({ genre: 'classic', html: `
      <button class="game-card" data-game="${g.id}">
        <div class="gc-icon">${g.icon}</div>
        <div class="gc-name">${g.name}</div>
        <div class="gc-tag">${g.tagline}</div>
        <div class="gc-meta">
          <span class="chip">${g.level}</span>
          <span class="chip">🃏 ${g.rules.length} rule cards</span>
          <span class="chip">${won ? '🏅 ' + won + '/' + g.botPresets.length + ' bots beaten' : '🤖 ' + g.botPresets.length + ' bots'}</span>
        </div>
      </button>` });
    });

    entries.push({ genre: 'board', html: `
      <a class="game-card" href="catan.html" style="text-decoration:none;color:inherit">
        <div class="gc-icon">🏝️</div>
        <div class="gc-name">Settlers of Catan <span class="chip" style="vertical-align:middle">engine: catanatron</span></div>
        <div class="gc-tag">The real rules, run by the <b>catanatron</b> engine. Tune a position-strength
        metric and a non-linear trade coefficient, then watch the policy deal turn-by-turn.</div>
        <div class="gc-meta">
          <span class="chip">advanced</span>
          <span class="chip">🤝 player trading</span>
          <span class="chip">🎛️ metric &amp; trade tuner</span>
        </div>
      </a>` });

    /* explorable-MDP catalog entries (chess, tetris, skat, ...);
     * playable ones already have a card above. */
    MDP.games.filter(e => !e.playable).forEach(e => {
      entries.push({ genre: e.genre, html: `
      <button class="game-card" data-explore="${e.id}">
        <div class="gc-icon">${e.icon}</div>
        <div class="gc-name">${e.name}</div>
        <div class="gc-tag">${e.blurb}</div>
        <div class="gc-meta">
          <span class="chip">browse the MDP</span>
          <span class="chip">engine: ${e.backend}</span>
          <span class="chip">${e.mdps.length} state spaces</span>
        </div>
      </button>` });
    });

    COMING_SOON.forEach(c => entries.push({ genre: c.genre, html: `
      <div class="game-card locked">
        <div class="gc-icon">${c.icon}</div>
        <div class="gc-name">${c.name}</div>
        <div class="gc-tag">${c.blurb}</div>
        <div class="gc-meta"><span class="chip soon">🔒 coming soon — or add it yourself (see README)</span></div>
      </div>` }));

    const shown = genreFilter === 'all' ? entries : entries.filter(e => e.genre === genreFilter);
    const counts = {};
    entries.forEach(e => { counts[e.genre] = (counts[e.genre] || 0) + 1; });
    const genreBar = [{ id: 'all', name: 'All games' }, ...MDP.genres]
      .filter(g => g.id === 'all' || counts[g.id])
      .map(g => `<button class="genre-chip${genreFilter === g.id ? ' sel' : ''}" data-genre="${g.id}"
        ${g.desc ? `title="${g.desc}"` : ''}>${g.name}${g.id === 'all' ? '' : ' (' + counts[g.id] + ')'}</button>`)
      .join('');

    const showRegistry = genreFilter === 'all' || genreFilter === 'atari' || genreFilter === 'control';

    root().innerHTML = `
      <header class="hero">
        <div class="logo">🧪 Strategy Lab</div>
        <h1>Don't play the game.<br><span class="grad">Solve it.</span></h1>
        <p class="sub">Build a strategy out of simple rule cards and pit it against a bot
        over <b>${NGAMES} simulated games</b>. Whoever's policy wins more games wins the match.</p>
        <div class="steps">
          <div class="step"><span>1</span>🃏 Stack rule cards into a strategy</div>
          <div class="step"><span>2</span>🤖 Pick a bot to challenge</div>
          <div class="step"><span>3</span>📊 Simulate ${NGAMES} games &amp; read the stats</div>
        </div>
      </header>
      <nav class="genre-bar">${genreBar}</nav>
      <main class="games-grid">${shown.map(e => e.html).join('')}</main>
      ${showRegistry ? '<section class="panel gym-live" id="gym-live"></section>' : ''}
      <footer class="foot">Built to be extended — drop a new game file into <code>js/games/</code>. See the README.</footer>`;

    $$('.genre-chip').forEach(el =>
      el.addEventListener('click', () => { genreFilter = el.dataset.genre; showHome(); }));
    $$('.game-card[data-game]').forEach(el =>
      el.addEventListener('click', () => showLab(StrategyLab.getGame(el.dataset.game))));
    $$('.game-card[data-explore]').forEach(el =>
      el.addEventListener('click', () => showExplore(MDP.get(el.dataset.explore))));

    if (showRegistry) renderGymLive();
  }

  /* -------- the live Gymnasium registry (needs the Flask server) -------- */
  function fetchGymLive() {
    if (gymLive) return Promise.resolve(gymLive);
    return fetch('/api/gym/envs').then(r => r.json())
      .then(d => (gymLive = d))
      .catch(() => (gymLive = 'offline'));
  }

  function renderGymLive() {
    const host = $('#gym-live');
    if (!host) return;
    host.innerHTML = '<h2>Gymnasium registry <span class="h-sub">every env the vendored submodule provides</span></h2>' +
      '<p class="muted">loading&hellip;</p>';
    fetchGymLive().then(d => {
      const el = $('#gym-live');
      if (!el) return;                          // view changed meanwhile
      if (d === 'offline') {
        el.innerHTML = `<h2>Gymnasium registry</h2>
          <p class="hint">Start the server to browse the live registry of the vendored
          Gymnasium submodule: <code>uv run python server/app.py</code> and open
          <code>http://localhost:8000</code>. The catalog cards above work without it.</p>`;
        return;
      }
      const groups = (d.groups || []).map(g => `
        <div class="gym-group">
          <h3>${MDP.esc(g.namespace)} <span class="h-sub">${g.envs.length} envs</span></h3>
          <div class="chips">${g.envs.map(e => `<span class="chip">${MDP.esc(e)}</span>`).join('')}</div>
        </div>`).join('');
      const spiel = d.open_spiel
        ? `<p class="hint">OpenSpiel: ${d.open_spiel.available
            ? `${d.open_spiel.games.length} games available`
            : MDP.esc(d.open_spiel.note || 'not built')}</p>`
        : '';
      el.innerHTML = `<h2>Gymnasium registry
          <span class="h-sub">live from the submodule — gymnasium ${MDP.esc(d.version || '?')}</span></h2>
        ${groups || '<p class="muted">registry came back empty.</p>'}${spiel}`;
    });
  }

  /* ============================= EXPLORE =============================
   * Browse-only view of a catalog game: what it is, where history
   * bites, and the collapsed-but-changeable MDP panel. */
  function showExplore(e) {
    game = null;
    root().innerHTML = `
      <header class="bar">
        <button class="ghost" id="back">&lsaquo; All games</button>
        <div class="bar-title">${e.icon} ${e.name}</div>
        <div class="bar-spacer"></div>
        <span class="chip">engine: ${MDP.esc(e.backend)}</span>
        <span class="chip">${e.players} player${e.players === 1 ? '' : 's'}</span>
      </header>
      <main class="duo explore">
        <section class="panel">
          <h2>About</h2>
          <p class="insight">${MDP.esc(e.blurb)}</p>
          <h3>Where history bites</h3>
          <p class="lens-verdict">${MDP.esc(e.history)}</p>
          <p class="hint">Browse-only skeleton: playing and training run in the Python
          backend on the vendored <b>${MDP.esc(e.backend)}</b> submodule
          (env: <code>${MDP.esc(e.envId)}</code>) — not wired up yet.</p>
          <p class="hint" id="env-check"></p>
        </section>
        <section class="panel">
          <h2>The MDP <span class="h-sub">state space is a design decision — pick one</span></h2>
          <div id="mdp-host"></div>
        </section>
      </main>`;

    $('#back').addEventListener('click', showHome);
    renderMdpHost(e, false);

    if (e.backend === 'gymnasium') {
      fetchGymLive().then(d => {
        const chk = $('#env-check');
        if (!chk || d === 'offline') return;
        const all = (d.groups || []).flatMap(g => g.envs);
        chk.innerHTML = all.includes(e.envId)
          ? `<code>${MDP.esc(e.envId)}</code> verified in the local Gymnasium registry.`
          : `<code>${MDP.esc(e.envId)}</code> is not in the local registry (extra
             dependency, e.g. <code>ale-py</code> for Atari).`;
      });
    }
  }

  function renderMdpHost(e, open) {
    const host = $('#mdp-host');
    host.innerHTML = MDP.panelHTML(e, MDP.selectedMdp(e.id), { open });
    MDP.bindPanel(host, e, () => renderMdpHost(e, true));
  }

  /* ============================= LAB ============================= */
  function showLab(g) {
    game = g;
    const userIds = userIdsFor(g);
    const preset = presetFor(g);

    const palette = g.rules.map(r => {
      const added = userIds.includes(r.id);
      return `
      <div class="rule-card${added ? ' added' : ''}" data-rule="${r.id}">
        <div class="rule-icon">${r.icon}</div>
        <div class="rule-main">
          <div class="rule-name">${r.name} ${badge(r.kind)}</div>
          <div class="rule-desc">${r.desc}</div>
        </div>
        <div class="rule-add">${added ? '✓' : '+'}</div>
      </div>`;
    }).join('');

    const stackItems = userIds.map((id, i) => {
      const r = g.rules.find(x => x.id === id);
      return `
      <li class="stack-item" draggable="true" data-i="${i}">
        <span class="prio">${i + 1}</span>
        <span class="s-icon">${r.icon}</span>
        <span class="s-name">${r.name} ${badge(r.kind)}</span>
        <span class="s-ctl">
          <button data-act="up" title="higher priority">▲</button>
          <button data-act="down" title="lower priority">▼</button>
          <button data-act="del" title="remove">✕</button>
        </span>
      </li>`;
    }).join('');

    const personas = g.botPresets.map(p => `
      <button class="persona${p.id === preset.id ? ' sel' : ''}" data-bot="${p.id}">
        <span class="p-icon">${p.icon}</span>
        <span class="p-head"><span class="p-name">${p.name}${(beaten[g.id] || {})[p.id] ? ' 🏅' : ''}</span>
        <span class="p-stars">${stars(p.stars)}</span></span>
        <span class="p-desc">${p.desc}</span>
      </button>`).join('');

    const botStack = preset.ruleIds.length
      ? preset.ruleIds.map((id, i) => {
          const r = g.rules.find(x => x.id === id);
          return `<li><span class="prio mini">${i + 1}</span>${r.icon} ${r.name} ${badge(r.kind)}</li>`;
        }).join('')
      : '<li class="muted">🎲 Pure chaos — random moves only.</li>';

    root().innerHTML = `
      <header class="bar">
        <button class="ghost" id="back">‹ All games</button>
        <div class="bar-title">${g.icon} ${g.name}</div>
        <div class="bar-spacer"></div>
      </header>
      <p class="howto">Your strategy is a <b>priority list</b>, read top to bottom every turn:
      ${badge('pick')} cards choose a move, ${badge('avoid')} cards veto options for the cards
      below. The first card that can decide, decides. If none can — 🎲 random.</p>
      <main class="lab">
        <section class="panel">
          <h2>🃏 Rule cards <span class="h-sub">tap to add</span></h2>
          <div id="palette">${palette}</div>
        </section>
        <section class="panel">
          <h2>🧠 Your strategy <span class="h-sub">drag to reorder</span></h2>
          <ol id="stack" class="stack">${stackItems ||
            '<li class="empty">No rules yet — you would play pure random.<br>Tap cards on the left to build your policy.</li>'}</ol>
          <div class="lucky"><span class="prio">∞</span>🎲 Lucky pick — random legal move <span class="h-sub">always last</span></div>
        </section>
        <section class="panel">
          <h2>🤖 Opponent</h2>
          <div id="personas">${personas}</div>
          <h3>Their strategy <span class="h-sub">study it, steal from it</span></h3>
          <ol class="bot-stack">${botStack}</ol>
          <button class="btn-run" id="run">▶ &nbsp;Play ${NGAMES} games</button>
          <button class="btn-play" id="play" title="play the games yourself, turn by turn">Play it yourself — turn by turn</button>
        </section>
      </main>`;

    $('#back').addEventListener('click', showHome);
    $('#run').addEventListener('click', runMatch);
    $('#play').addEventListener('click', () =>
      Play.open(g, userIdsFor(g), presetFor(g), { onBack: () => showLab(g) }));

    $('#palette').addEventListener('click', e => {
      const card = e.target.closest('.rule-card');
      if (!card || card.classList.contains('added')) return;
      userIdsFor(g).push(card.dataset.rule);
      saveStore(); showLab(g);
    });

    const stackEl = $('#stack');
    stackEl.addEventListener('click', e => {
      const btn = e.target.closest('button[data-act]');
      if (!btn) return;
      const li = btn.closest('.stack-item');
      const i = +li.dataset.i;
      const ids = userIdsFor(g);
      if (btn.dataset.act === 'del') ids.splice(i, 1);
      else if (btn.dataset.act === 'up' && i > 0) [ids[i - 1], ids[i]] = [ids[i], ids[i - 1]];
      else if (btn.dataset.act === 'down' && i < ids.length - 1) [ids[i + 1], ids[i]] = [ids[i], ids[i + 1]];
      saveStore(); showLab(g);
    });
    $$('.stack-item', stackEl).forEach(li => {
      li.addEventListener('dragstart', () => { dragIndex = +li.dataset.i; li.classList.add('dragging'); });
      li.addEventListener('dragend', () => li.classList.remove('dragging'));
      li.addEventListener('dragover', e => e.preventDefault());
      li.addEventListener('drop', e => {
        e.preventDefault();
        const to = +li.dataset.i;
        if (dragIndex === null || dragIndex === to) return;
        const ids = userIdsFor(g);
        const [moved] = ids.splice(dragIndex, 1);
        ids.splice(to, 0, moved);
        dragIndex = null;
        saveStore(); showLab(g);
      });
    });

    $('#personas').addEventListener('click', e => {
      const p = e.target.closest('.persona');
      if (!p) return;
      bots[g.id] = p.dataset.bot;
      saveStore(); showLab(g);
    });
  }

  /* ============================= MATCH ============================= */
  function runMatch() {
    const g = game;
    const userIds = [...userIdsFor(g)];
    const preset = presetFor(g);
    const seed = (Math.random() * 0x7fffffff) >>> 0;
    const { results } = StrategyLab.simulateMatch(g, userIds, preset.ruleIds, NGAMES, seed);
    const st = computeStats(results);
    if (st.u > st.b) {
      (beaten[g.id] = beaten[g.id] || {})[preset.id] = true;
      saveStore();
    }
    last = { g, userIds, botIds: [...preset.ruleIds], preset, seed, results, st };
    showResults();
  }

  function computeStats(results) {
    const n = results.length;
    let u = 0, b = 0, d = 0, turnsSum = 0;
    let firstU = -1, firstB = -1, firstD = -1;
    let curU = 0, curB = 0, maxU = 0, maxB = 0;
    let longestT = -1, longestI = -1;
    let uStartWins = 0, uStartGames = 0, uSecondWins = 0, uSecondGames = 0;
    const series = [0];
    let lead = 0;
    results.forEach((r, i) => {
      turnsSum += r.turns;
      if (r.turns > longestT) { longestT = r.turns; longestI = i; }
      if (r.firstSeat === 0) uStartGames++; else uSecondGames++;
      if (r.winner === 0) {
        u++; if (firstU < 0) firstU = i;
        curU++; curB = 0; lead++;
        if (r.firstSeat === 0) uStartWins++; else uSecondWins++;
      } else if (r.winner === 1) {
        b++; if (firstB < 0) firstB = i;
        curB++; curU = 0; lead--;
      } else {
        d++; if (firstD < 0) firstD = i;
        curU = 0; curB = 0;
      }
      maxU = Math.max(maxU, curU); maxB = Math.max(maxB, curB);
      series.push(lead);
    });
    return {
      n, u, b, d, avgTurns: turnsSum / n, firstU, firstB, firstD,
      maxU, maxB, longestI, longestT, series,
      uStartWins, uStartGames, uSecondWins, uSecondGames,
    };
  }

  /* ============================= RESULTS ============================= */
  function momentumSVG(series) {
    const n = series.length - 1;
    let min = 0, max = 0;
    series.forEach(v => { min = Math.min(min, v); max = Math.max(max, v); });
    const W = 600, H = 170, pad = 12;
    const span = Math.max(max - min, 4);
    const x = i => pad + (i * (W - 2 * pad)) / n;
    const y = v => pad + ((max - v) * (H - 2 * pad)) / span;
    const pts = series.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const final = series[series.length - 1];
    const cls = final > 0 ? 'mom-you' : final < 0 ? 'mom-bot' : 'mom-tie';
    return `
      <svg class="momentum ${cls}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <line class="zero" x1="${pad}" y1="${y(0)}" x2="${W - pad}" y2="${y(0)}"/>
        <polygon class="area" points="${x(0)},${y(0)} ${pts} ${x(n).toFixed(1)},${y(0)}"/>
        <polyline class="line" points="${pts}"/>
      </svg>
      <div class="mom-labels"><span>↑ you ahead</span><span>↓ ${last.preset.name} ahead</span></div>`;
  }

  function genericInsight(st, preset) {
    const diff = st.u - st.b;
    if (diff > 40) return `Total domination — your strategy takes ${st.u} of ${st.n} games. ` +
      `${preset.name} has nothing. Time to challenge a stronger bot.`;
    if (diff > 10) return `A clear edge: your rule priorities read the game better than ` +
      `${preset.name}'s over a big sample. Can you stretch the gap further by reordering?`;
    if (diff >= -10) return `Statistically a coin flip — over ${st.n} games neither policy ` +
      `proved better. Tweak one priority at a time and rematch: that is policy iteration, by hand.`;
    if (diff >= -40) return `${preset.name} reads the game better right now. Study the bot's ` +
      `stack in the lab — which of its priorities is your strategy missing?`;
    return `Rough night. ${preset.name} won ${st.b} of ${st.n}. Steal the bot's ordering ` +
      `wholesale, then try to improve on it — standing on shoulders is allowed here.`;
  }

  function showResults() {
    const { g, st, preset } = last;
    const banner = st.u > st.b
      ? { cls: 'win', big: '🏆 You win the match!' }
      : st.u < st.b
        ? { cls: 'lose', big: `🤖 ${preset.name} wins the match` }
        : { cls: 'tie', big: '🤝 Dead heat!' };

    const bar = (label, cls, count) => `
      <div class="score-row">
        <span class="who ${cls}">${label}</span>
        <div class="bar"><div class="fill ${cls}" data-w="${(count / st.n) * 100}"></div></div>
        <span class="num" data-n="${count}">0</span>
      </div>`;

    const insight = (g.insight && g.insight({
      userWins: st.u, botWins: st.b, draws: st.d, n: st.n,
      userRuleIds: last.userIds, botPresetId: preset.id,
    })) || genericInsight(st, preset);

    const chips = [
      `⏱ avg game: ${st.avgTurns.toFixed(1)} moves`,
      `🔥 your best streak: ${st.maxU}`,
      `🤖 bot's best streak: ${st.maxB}`,
      `🎬 starting first you won ${st.uStartWins}/${st.uStartGames} · second ${st.uSecondWins}/${st.uSecondGames}`,
    ].map(c => `<span class="chip">${c}</span>`).join('');

    const seen = new Set();
    const reps = [];
    const addRep = (idx, label) => {
      if (idx >= 0 && !seen.has(idx)) { seen.add(idx); reps.push({ idx, label }); }
    };
    addRep(st.firstU, `Game ${st.firstU + 1} — your first win`);
    addRep(st.firstB, `Game ${st.firstB + 1} — ${preset.name}'s first win`);
    addRep(st.firstD, `Game ${st.firstD + 1} — a draw`);
    addRep(st.longestI, `Game ${st.longestI + 1} — longest game (${st.longestT} moves)`);

    root().innerHTML = `
      <header class="bar">
        <button class="ghost" id="back-lab">‹ Strategy</button>
        <div class="bar-title">${g.icon} ${g.name} — results</div>
        <button class="ghost" id="home">🏠</button>
      </header>
      <section class="banner ${banner.cls}">
        <div class="b-big">${banner.big}</div>
        <div class="b-score">${st.u} : ${st.b} <span>· ${st.d} draws · ${st.n} games · starting player alternated</span></div>
      </section>
      <section class="panel scoreboard">
        ${bar('🧑 You', 'you', st.u)}
        ${bar('🤝 Draws', 'draw', st.d)}
        ${bar(`${preset.icon} ${preset.name}`, 'bot', st.b)}
      </section>
      <section class="duo">
        <div class="panel"><h2>📈 Momentum</h2>${momentumSVG(st.series)}
          <p class="hint">Cumulative lead (your wins − bot wins) across all ${st.n} games.</p></div>
        <div class="panel"><h2>🔍 Insight</h2><p class="insight">${insight}</p>
          <div class="chips">${chips}</div></div>
      </section>
      <section class="panel">
        <h2>🎬 Watch a sample game</h2>
        <div class="replay-btns">${reps.map(r =>
          `<button class="rep-btn" data-idx="${r.idx}">▶ ${r.label}</button>`).join('') ||
          '<span class="muted">No games to show.</span>'}</div>
      </section>
      <div class="actions">
        <button class="btn-sec" id="tweak">🛠 Tweak strategy</button>
        <button class="btn-sec" id="rematch">🔁 Rematch (new dice)</button>
        <button class="btn-sec" id="home2">🏠 All games</button>
      </div>`;

    // animate bars + counters
    requestAnimationFrame(() => requestAnimationFrame(() => {
      $$('.fill').forEach(f => { f.style.width = f.dataset.w + '%'; });
      $$('.num').forEach(el => countUp(el, +el.dataset.n));
    }));

    $('#back-lab').addEventListener('click', () => showLab(g));
    $('#tweak').addEventListener('click', () => showLab(g));
    $('#rematch').addEventListener('click', () => { game = g; runMatch(); });
    $('#home').addEventListener('click', showHome);
    $('#home2').addEventListener('click', showHome);
    $$('.rep-btn').forEach(btn => {
      const r = reps.find(x => x.idx === +btn.dataset.idx);
      btn.addEventListener('click', () => openReplay(r.idx, r.label));
    });
  }

  function countUp(el, to) {
    const t0 = performance.now(), dur = 900;
    (function frame(t) {
      const k = Math.min(1, (t - t0) / dur);
      el.textContent = Math.round(to * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(frame);
    })(t0);
  }

  /* ============================= REPLAY ============================= */
  function openReplay(idx, title) {
    const { g, userIds, botIds, preset, seed } = last;
    const rep = StrategyLab.replayGame(g, userIds, botIds, idx, seed);
    const frames = rep.replay;
    let i = 0, timer = null;

    const result = rep.winner === 0 ? '🏆 you won this one'
      : rep.winner === 1 ? `🤖 ${preset.name} won this one`
        : rep.timeout ? '⏱ cut off — draw' : '🤝 draw';

    const back = document.createElement('div');
    back.className = 'modal-back';
    back.innerHTML = `
      <div class="modal">
        <div class="modal-head">
          <div>${title} <span class="muted">· ${result}</span></div>
          <button id="m-close">✕</button>
        </div>
        <div class="board" id="m-board"></div>
        <div class="caption" id="m-cap"></div>
        <div class="m-ctl">
          <button id="m-first" title="start">⏮</button>
          <button id="m-prev" title="back">◀</button>
          <button id="m-play" title="play">▶</button>
          <button id="m-next" title="forward">⏭</button>
          <input type="range" id="m-slider" min="0" max="${frames.length - 1}" value="0">
          <span id="m-step"></span>
        </div>
      </div>`;
    document.body.appendChild(back);

    const boardEl = $('#m-board', back);
    const capEl = $('#m-cap', back);
    const slider = $('#m-slider', back);
    const stepEl = $('#m-step', back);
    const playBtn = $('#m-play', back);

    function setFrame(j) {
      i = Math.max(0, Math.min(frames.length - 1, j));
      const f = frames[i];
      g.renderState(f.state, boardEl);
      capEl.innerHTML = f.seat === null
        ? `<span class="muted">${f.caption}</span>`
        : `<b class="cap${f.seat}">${f.seat === 0 ? 'You' : preset.name}</b> ${f.caption}`;
      slider.value = i;
      stepEl.textContent = `${i}/${frames.length - 1}`;
      if (i === frames.length - 1) stop();
    }
    function stop() {
      if (timer) { clearInterval(timer); timer = null; playBtn.textContent = '▶'; }
    }
    function play() {
      if (timer) { stop(); return; }
      if (i >= frames.length - 1) setFrame(0);
      playBtn.textContent = '⏸';
      timer = setInterval(() => {
        if (i < frames.length - 1) setFrame(i + 1); else stop();
      }, 650);
    }
    function close() { stop(); back.remove(); }

    $('#m-close', back).addEventListener('click', close);
    back.addEventListener('click', e => { if (e.target === back) close(); });
    $('#m-first', back).addEventListener('click', () => { stop(); setFrame(0); });
    $('#m-prev', back).addEventListener('click', () => { stop(); setFrame(i - 1); });
    $('#m-next', back).addEventListener('click', () => { stop(); setFrame(i + 1); });
    playBtn.addEventListener('click', play);
    slider.addEventListener('input', () => { stop(); setFrame(+slider.value); });

    setFrame(0);
    play();
  }

  /* ============================= BOOT ============================= */
  function init() {
    loadStore();
    showHome();
  }

  return { init };
})();
