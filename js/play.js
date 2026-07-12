/* ============================================================
 * Strategy Lab — Play mode.
 *
 * Instead of only *designing* a policy, you sit down and play the
 * game yourself, turn by turn, against a bot. While you play you
 * look at the game through one of two lenses (toggle live):
 *
 *   CARDS  the strategy-card lens: your stack is annotated with
 *          "which card would decide right now, and what would it
 *          play" — you explore the cards by playing.
 *
 *   RL     the reinforcement-learning lens (a skeleton for now):
 *          the same game described as an MDP — states, actions,
 *          rewards — with symmetry folding shown live on the
 *          current position (opening: 9 moves -> 3 real decisions:
 *          center, corner, edge). Training itself will run in a
 *          Python backend on Gymnasium / OpenSpiel (both vendored
 *          as submodules); nothing is wired up yet.
 *
 * A session spans the usual 100 games. Play as many by hand as you
 * like, then hit auto-finish and your card stack plays the rest at
 * simulation speed — same seeds and seat alternation as a normal
 * simulated match.
 *
 * Pure logic (D4 symmetry, decision tracing) sits on top with no
 * DOM access, so node can test it (see test/smoke.js).
 * ============================================================ */
window.Play = (function () {
  'use strict';

  const SL = window.StrategyLab;
  const NGAMES = 100;

  /* ================= D4 symmetry on the 3x3 board (pure) ==========
   * A transform is a permutation P with apply(board)[i] = board[P[i]].
   * The full group is generated from a quarter turn and a mirror. */
  const ROT90 = [6, 3, 0, 7, 4, 1, 8, 5, 2];
  const FLIPH = [2, 1, 0, 5, 4, 3, 8, 7, 6];

  const D4 = (() => {
    const id = [0, 1, 2, 3, 4, 5, 6, 7, 8];
    const seen = new Map([[id.join(','), id]]);
    const queue = [id];
    while (queue.length) {
      const p = queue.pop();
      for (const g of [ROT90, FLIPH]) {
        const q = p.map((_, i) => p[g[i]]);      // q = g after p
        const key = q.join(',');
        if (!seen.has(key)) { seen.set(key, q); queue.push(q); }
      }
    }
    return Array.from(seen.values());            // 8 transforms
  })();

  /* The transforms that leave this exact board unchanged. */
  function stabilizers(board) {
    return D4.filter(p => p.every((j, i) => board[j] === board[i]));
  }

  /* Group the legal moves into symmetry-equivalence classes: two
   * moves are "the same decision" iff a transform that fixes the
   * board maps one square onto the other. Returns [{cells, rep}]. */
  function moveClasses(board, legal) {
    const stab = stabilizers(board);
    const parent = {};
    legal.forEach(m => { parent[m] = m; });
    const find = m => (parent[m] === m ? m : (parent[m] = find(parent[m])));
    const union = (a, b) => { parent[find(a)] = find(b); };
    for (const p of stab) for (const m of legal) {
      if (parent[p[m]] !== undefined) union(m, p[m]);
    }
    const byRoot = new Map();
    for (const m of legal) {
      const r = find(m);
      if (!byRoot.has(r)) byRoot.set(r, []);
      byRoot.get(r).push(m);
    }
    return Array.from(byRoot.values()).map(cells => ({ cells, rep: Math.min(...cells) }));
  }

  const TTT_CELL_KIND = i => (i === 4 ? 'center' : [0, 2, 6, 8].includes(i) ? 'corner' : 'edge');
  const TTT_COUNTS = { reachable: 5478, folded: 765 };   // verified in the Rust lab's tests

  /* Opening fold: on the empty board 9 squares collapse to 3 classes. */
  function openingClasses() {
    return moveClasses(Array(9).fill(null), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
  }

  /* ============ trace a card-stack decision (pure) =================
   * Same stepping as the engine's chooseMove, but reports *which*
   * card decides — the live hint of the cards lens. The rng is a
   * fixed dummy: hints must not consume the real game rng. */
  function traceDecision(game, state, stackIds, seat) {
    const stack = SL.resolveStack(game, stackIds);
    let candidates = game.legalMoves(state);
    if (candidates.length === 0) return { move: null, rule: null, pass: true, random: false };
    const rng = SL.mulberry32(20260710);
    for (const rule of stack) {
      if (candidates.length === 1) break;
      if (rule.kind === 'avoid') {
        const kept = candidates.filter(m => !rule.avoid(state, m, seat));
        if (kept.length > 0) candidates = kept;
      } else {
        const m = rule.pick(state, candidates, seat, rng);
        if (m !== null && m !== undefined) return { move: m, rule, pass: false, random: false };
      }
    }
    if (candidates.length === 1) return { move: candidates[0], rule: null, pass: false, random: false, forced: true };
    return { move: null, rule: null, pass: false, random: true, candidates };
  }

  /* ======================= session state ========================= */
  let S = null;        // the active play session
  let timerToken = 0;  // bumping it cancels any pending bot timer

  function open(g, userIds, preset, opts) {
    timerToken++;                 // orphan any timer of a previous session
    S = {
      g,
      userIds: [...userIds],
      preset,
      botStack: SL.resolveStack(g, preset.ruleIds),
      onBack: (opts && opts.onBack) || (() => {}),
      seed: (Math.random() * 0x7fffffff) >>> 0,
      k: 0,                 // index of the game being played (0-based)
      results: [],          // {winner, turns, timeout, firstSeat, manual}
      handPlayed: 0,
      mode: 'cards',        // 'cards' | 'rl'
      detailsOpen: {},      // keep <details> state across re-renders
      finished: false,
      state: null, rng: null, over: false, turns: 0, lastCaption: null,
    };
    startGame();
  }

  /* Same seed/seat scheme as the engine's simulateMatch, so the
   * auto-finished tail is exactly the match you would have simulated. */
  const gameSeed = (seed, i) => (seed + i * 7919) >>> 0;

  function startGame() {
    const s = S;
    s.rng = SL.mulberry32(gameSeed(s.seed, s.k));
    s.state = s.g.initialState(s.rng, s.k % 2);
    s.over = false;
    s.turns = 0;
    s.lastCaption = null;
    render();
    scheduleAuto();
  }

  /* Bot turns (and forced passes) advance by themselves; human
   * turns wait for input. */
  function scheduleAuto() {
    const s = S;
    if (!s || s.over || s.finished) return;
    const seat = s.g.currentPlayer(s.state);
    const legal = s.g.legalMoves(s.state);
    if (seat === 0 && legal.length > 0) return;   // human's move — wait
    const t = ++timerToken;
    setTimeout(() => {
      if (t !== timerToken || !S || S.over || S.finished) return;
      const move = seat === 1 && legal.length > 0
        ? SL.chooseMove(s.g, s.state, s.botStack, 1, s.rng)
        : null;                                   // no legal move: pass
      doMove(move);
    }, 420);
  }

  function humanMove(move) {
    const s = S;
    if (!s || s.over || s.finished) return;
    if (s.g.currentPlayer(s.state) !== 0) return;
    doMove(move);
  }

  function doMove(move) {
    const s = S;
    const seat = s.g.currentPlayer(s.state);
    let text;
    try { text = s.g.describeMove(s.state, move, seat); }
    catch (e) { text = 'has no legal move and passes'; }
    s.lastCaption = { seat, text };
    s.state = s.g.applyMove(s.state, move, s.rng);
    s.turns++;
    if (s.g.isTerminal(s.state) || s.turns >= (s.g.maxTurns || 2000)) endGame();
    else { render(); scheduleAuto(); }
  }

  function endGame() {
    const s = S;
    s.over = true;
    const terminal = s.g.isTerminal(s.state);
    const winner = terminal
      ? s.g.winner(s.state)
      : (s.g.timeoutWinner ? s.g.timeoutWinner(s.state) : null);
    s.results.push({ winner, turns: s.turns, timeout: !terminal, firstSeat: s.k % 2, manual: true });
    s.handPlayed++;
    render();
  }

  function nextGame() {
    const s = S;
    if (!s.over) return;
    s.k++;
    if (s.k >= NGAMES) { s.finished = true; render(); }
    else startGame();
  }

  /* Hand the remaining games to your card stack, at simulation speed. */
  function autoFinish() {
    const s = S;
    timerToken++;                              // cancel any pending bot move
    const stacks = [SL.resolveStack(s.g, s.userIds), s.botStack];
    const from = s.over ? s.k + 1 : s.k;       // an unfinished game is re-run
    for (let i = from; i < NGAMES; i++) {
      const r = SL.playGame(s.g, stacks, i % 2, gameSeed(s.seed, i), false);
      s.results.push({ winner: r.winner, turns: r.turns, timeout: r.timeout, firstSeat: i % 2, manual: false });
    }
    s.k = NGAMES;
    s.finished = true;
    render();
  }

  function tallyOf(results) {
    let u = 0, b = 0, d = 0;
    for (const r of results) {
      if (r.winner === 0) u++; else if (r.winner === 1) b++; else d++;
    }
    return { u, b, d, n: results.length };
  }

  /* ========================= rendering =========================== */
  const root = () => document.getElementById('app');
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function render() {
    const s = S;
    if (s.finished) { renderSummary(); return; }

    const t = tallyOf(s.results);
    const bar = `
      <header class="bar">
        <button class="ghost" id="p-back">&lsaquo; Strategy</button>
        <div class="bar-title">${s.g.icon} ${s.g.name} — you vs ${esc(s.preset.name)}</div>
        <div class="tally">game ${Math.min(s.k + 1, NGAMES)} / ${NGAMES} &middot;
          <b class="lab0">you ${t.u}</b> &middot; draws ${t.d} &middot; <b class="lab1">${esc(s.preset.name)} ${t.b}</b></div>
      </header>`;

    root().innerHTML = `
      ${bar}
      <main class="play">
        <section class="panel play-board">
          <div id="p-board"></div>
          <div class="play-status" id="p-status"></div>
          <div class="move-btns" id="p-moves"></div>
          <div class="play-actions" id="p-actions"></div>
        </section>
        <section class="panel">
          <div class="mode-toggle">
            <button class="mode-btn${s.mode === 'cards' ? ' sel' : ''}" data-mode="cards">Strategy cards</button>
            <button class="mode-btn${s.mode === 'rl' ? ' sel' : ''}" data-mode="rl">RL / MDP</button>
          </div>
          <div id="p-lens">${s.mode === 'cards' ? cardsLensHTML() : rlLensHTML()}</div>
        </section>
      </main>`;

    $('#p-back').addEventListener('click', () => { timerToken++; S = null; s.onBack(); });
    $$('.mode-btn').forEach(b => b.addEventListener('click', () => { s.mode = b.dataset.mode; render(); }));
    $$('#p-lens details').forEach(d => d.addEventListener('toggle', () => { s.detailsOpen[d.dataset.d] = d.open; }));

    renderBoard();
    renderStatus();
    renderActions();
  }

  function renderBoard() {
    const s = S;
    const boardEl = $('#p-board');
    s.g.renderState(s.state, boardEl);

    const movesEl = $('#p-moves');
    movesEl.innerHTML = '';
    if (s.over) return;
    if (s.g.currentPlayer(s.state) !== 0) return;
    const legal = s.g.legalMoves(s.state);
    if (legal.length === 0) return;             // scheduleAuto passes for us

    /* If the game can take clicks on the board itself, use that;
     * otherwise offer every legal move as a button. */
    if (s.g.bindPlayInput && s.g.bindPlayInput(s.state, boardEl, legal, humanMove)) return;
    legal.forEach((m, i) => {
      const btn = document.createElement('button');
      btn.className = 'move-btn';
      btn.textContent = s.g.describeMove(s.state, m, 0);
      btn.addEventListener('click', () => humanMove(legal[i]));
      movesEl.appendChild(btn);
    });
  }

  function renderStatus() {
    const s = S;
    const el = $('#p-status');
    const last = s.lastCaption
      ? `<div class="muted">${s.lastCaption.seat === 0 ? '<b class="lab0">You</b>' : '<b class="lab1">' + esc(s.preset.name) + '</b>'} ${esc(s.lastCaption.text)}</div>`
      : '';
    if (s.over) {
      const r = s.results[s.results.length - 1];
      const msg = r.winner === 0 ? { cls: 'win', t: 'You win this game' }
        : r.winner === 1 ? { cls: 'lose', t: `${s.preset.name} wins this game` }
          : { cls: 'draw', t: r.timeout ? 'Cut off — a draw' : 'A draw' };
      el.innerHTML = `${last}<div class="play-banner ${msg.cls}">${esc(msg.t)}</div>`;
    } else if (s.g.currentPlayer(s.state) === 0) {
      el.innerHTML = `${last}<div><b class="lab0">Your move</b></div>`;
    } else {
      el.innerHTML = `${last}<div class="muted">${esc(s.preset.name)} is thinking&hellip;</div>`;
    }
  }

  function renderActions() {
    const s = S;
    const el = $('#p-actions');
    const remaining = NGAMES - s.k - (s.over ? 1 : 0);
    el.innerHTML = `
      ${s.over && s.k + 1 < NGAMES ? '<button class="btn-sec" id="p-next">Next game</button>' : ''}
      ${s.over && s.k + 1 >= NGAMES ? '<button class="btn-sec" id="p-next">See the final tally</button>' : ''}
      ${remaining > 0 ? `<button class="btn-sec" id="p-auto" title="your card stack plays the rest">Auto-finish ${remaining} games</button>` : ''}`;
    const nxt = $('#p-next'); if (nxt) nxt.addEventListener('click', nextGame);
    const auto = $('#p-auto'); if (auto) auto.addEventListener('click', autoFinish);
  }

  /* ------------------- the CARDS lens ------------------- */
  function cardsLensHTML() {
    const s = S;
    const yourTurn = !s.over && s.g.currentPlayer(s.state) === 0 && s.g.legalMoves(s.state).length > 0;
    const trace = yourTurn ? traceDecision(s.g, s.state, s.userIds, 0) : null;

    const items = s.userIds.map((id, i) => {
      const r = s.g.rules.find(x => x.id === id);
      const fires = trace && trace.rule && trace.rule.id === id;
      const hint = fires ? `<div class="hint-line">would play: ${esc(s.g.describeMove(s.state, trace.move, 0).replace(/^places /, ''))}</div>` : '';
      return `<li class="stack-item${fires ? ' fires' : ''}">
        <span class="prio">${i + 1}</span>
        <span class="s-icon">${r.icon}</span>
        <span class="s-name">${esc(r.name)}${hint}</span></li>`;
    }).join('');

    let verdict = '';
    if (trace) {
      if (trace.rule) verdict = `<p class="lens-verdict">Your top deciding card right now: <b>${esc(trace.rule.name)}</b>. Do you agree with it?</p>`;
      else if (trace.random) verdict = `<p class="lens-verdict">No card in your stack can decide here — the stack would fall through to a <b>random</b> pick among ${trace.candidates.length} moves. A card is missing.</p>`;
      else verdict = '<p class="lens-verdict">Only one legal move — nothing to decide.</p>';
    } else if (!s.over) {
      verdict = '<p class="lens-verdict muted">Waiting for the bot&hellip;</p>';
    }

    return `
      <div class="mode-note">The strategy-card lens: a policy is a priority list, read top to
      bottom. While you play, your stack shows <b>which card would decide right now</b> —
      play a few games and you learn what each card is for.</div>
      ${s.userIds.length
        ? `<ol class="stack lens-stack">${items}</ol>`
        : '<p class="lens-verdict">Your stack is empty — you are playing on instinct alone. Build cards in the lab and they will light up here.</p>'}
      ${verdict}
      <h3>Opponent</h3>
      <p class="lens-verdict">${s.preset.icon} <b>${esc(s.preset.name)}</b> — ${esc(s.preset.desc)}</p>`;
  }

  /* ------------------- the RL lens (skeleton) ------------------- */
  function det(id, summary, body) {
    const open = S.detailsOpen[id] ? ' open' : '';
    return `<details data-d="${id}"${open}><summary>${summary}</summary>${body}</details>`;
  }

  function rlLensHTML() {
    const s = S;
    const head = `
      <div class="mode-note">The reinforcement-learning lens — <b>a skeleton for now</b>.
      The plan: an agent trains against this game in a Python backend
      (<code>Gymnasium</code> / <code>OpenSpiel</code>, already vendored as submodules) and
      you watch its value function converge. Until that is wired up, this panel defines
      the playground the agent will see: the <b>MDP</b>.</div>`;

    if (s.g.id !== 'tictactoe') {
      return `${head}
        <p class="lens-verdict">The MDP view is drafted for <b>Tic-Tac-Toe</b> first —
        switch to it to see states, actions, rewards and symmetry folding live.
        ${esc(s.g.name)} gets its own definition once the backend lands.</p>`;
    }

    const board = s.state.board;
    const legal = s.g.legalMoves(s.state);
    const classes = s.over ? [] : moveClasses(board, legal);
    const classOf = {};
    classes.forEach((c, ci) => c.cells.forEach(m => { classOf[m] = ci; }));

    const mini = board.map((v, i) => {
      if (v !== null) return `<div class="sym-cell taken">${s.state.marks[v]}</div>`;
      const ci = classOf[i];
      if (ci === undefined) return '<div class="sym-cell"></div>';
      return `<div class="sym-cell" style="background:hsl(${(ci * 67 + 210) % 360} 45% 26%);border-color:hsl(${(ci * 67 + 210) % 360} 55% 45%)">${ci + 1}</div>`;
    }).join('');

    const symLine = s.over
      ? '<div class="sym-line">Game over — no decisions left.</div>'
      : `<div class="sym-line">${legal.length} legal move${legal.length === 1 ? '' : 's'}
           &rarr; <b>${classes.length}</b> real decision${classes.length === 1 ? '' : 's'}</div>
         <p class="lens-small">Squares with the same number are <b>the same move</b>: a rotation or
         mirror of the board maps one onto the other, so an agent only needs to learn one of them.</p>`;

    const opening = openingClasses();  // 3 classes on the empty board
    return `${head}
      <h3>The game as an MDP</h3>
      <dl class="rl-dl">
        <dt>State s</dt><dd>the board, as seen by the player to move.
          ${TTT_COUNTS.reachable} reachable states; symmetry folds them to <b>${TTT_COUNTS.folded}</b>.</dd>
        <dt>Actions A(s)</dt><dd>the empty squares — folded into equivalence classes below.</dd>
        <dt>Transition</dt><dd>your mark lands (deterministic), then the opponent replies:
          from your seat, the opponent is part of the environment.</dd>
        <dt>Reward</dt><dd>+1 win &middot; 0 draw &middot; &minus;1 loss, only at the end
          (an episodic task, &gamma; = 1).</dd>
      </dl>
      <h3>Symmetry, live on this position</h3>
      ${symLine}
      <div class="sym-mini">${mini}</div>
      <p class="lens-small">The opening is the famous case: 9 squares, but only
      <b>${opening.length}</b> real choices — ${opening.map(c => TTT_CELL_KIND(c.rep)).join(', ')}.</p>
      ${det('tree', 'Where does the game tree fit?',
        `<p>From the empty board there are 255,168 ways a game can play out — the <b>game
         tree</b>. But many branches meet again: only ${TTT_COUNTS.reachable} distinct positions
         exist, and symmetry folds those to ${TTT_COUNTS.folded}. An RL agent never expands the
         whole tree; it <i>samples paths</i> through it and drags reward information backwards
         along them. That backed-up number per state is the value function.</p>`)}
      ${det('entropy', 'And entropy?',
        `<p>A policy assigns probabilities to moves. <b>Entropy</b> measures how spread out
         they are: picking uniformly among 9 opening squares is log<sub>2</sub>&nbsp;9 &asymp; 3.17 bits
         of unpredictability; always playing one square is 0 bits. Exploring = high entropy,
         committing = low. Symmetry already caps the <i>useful</i> opening entropy at
         log<sub>2</sub>&nbsp;3 &asymp; 1.58 bits — the rest is noise the fold removes for free.</p>`)}`;
  }

  /* ------------------- final tally ------------------- */
  function renderSummary() {
    const s = S;
    const t = tallyOf(s.results);
    const auto = t.n - s.handPlayed;
    const banner = t.u > t.b
      ? { cls: 'win', big: 'You take the match' }
      : t.u < t.b ? { cls: 'lose', big: `${s.preset.name} takes the match` }
        : { cls: 'tie', big: 'Dead heat' };
    const bar = (label, cls, count) => `
      <div class="score-row">
        <span class="who ${cls}">${label}</span>
        <div class="bar"><div class="fill ${cls}" style="width:${(count / Math.max(t.n, 1)) * 100}%"></div></div>
        <span class="num">${count}</span>
      </div>`;

    root().innerHTML = `
      <header class="bar">
        <button class="ghost" id="p-back">&lsaquo; Strategy</button>
        <div class="bar-title">${s.g.icon} ${s.g.name} — session over</div>
      </header>
      <section class="banner ${banner.cls}">
        <div class="b-big">${esc(banner.big)}</div>
        <div class="b-score">${t.u} : ${t.b} <span>&middot; ${t.d} draws &middot; ${t.n} games</span></div>
      </section>
      <section class="panel scoreboard">
        ${bar('You', 'you', t.u)}
        ${bar('Draws', 'draw', t.d)}
        ${bar(esc(s.preset.name), 'bot', t.b)}
        <p class="hint">You played ${s.handPlayed} game${s.handPlayed === 1 ? '' : 's'} by hand;
        ${auto > 0 ? `the other ${auto} ran on your card stack at simulation speed.` : 'every single one.'}</p>
      </section>
      <div class="actions">
        <button class="btn-sec" id="p-again">Play again</button>
        <button class="btn-sec" id="p-back2">Back to the lab</button>
      </div>`;

    const leave = () => { timerToken++; const cb = s.onBack; S = null; cb(); };
    $('#p-back').addEventListener('click', leave);
    $('#p-back2').addEventListener('click', leave);
    $('#p-again').addEventListener('click', () => open(s.g, s.userIds, s.preset, { onBack: s.onBack }));
  }

  /* Public surface: open() for the UI, the pure helpers for tests.
   * _debug drives the private flow headlessly (see test/). */
  return {
    open, D4, stabilizers, moveClasses, openingClasses, traceDecision, TTT_COUNTS, NGAMES,
    _debug: { autoFinish, nextGame, humanMove, lensCards: cardsLensHTML, lensRL: rlLensHTML, session: () => S },
  };
})();
