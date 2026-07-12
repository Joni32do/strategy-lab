/* ============================================================
 * Strategy Lab - live play against the Python backend.
 *
 * The catalog (js/mdp.js) only *describes* an environment. This
 * module lets you actually sit down and play it against the Flask
 * server (server/envs.py). Two kinds, mirroring the two backends:
 *
 *   gym    a single-agent Gymnasium env. Step it yourself with the
 *          action buttons, or flip "policy: random" and watch a
 *          random policy drive - the policy-exploration hook.
 *
 *   spiel  an n-player OpenSpiel game. You hold one seat; the other
 *          seats are random bots. Play a legal move, let a random
 *          move play for you, or autoplay the whole thing to the end.
 *
 * Everything that touches the network catches a hard failure and
 * shows a friendly "start the server" hint. The pure helpers (obs
 * formatting, log classing) are DOM-free and exported for tests.
 * ============================================================ */
window.EnvPlay = (function () {
  'use strict';

  /* --------------------------- session ---------------------------- */
  let S = null;        // the active play session (gym or spiel)
  let token = 0;       // bump to orphan pending timers / fetch callbacks

  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const randSeed = () => (Math.random() * 0x7fffffff) >>> 0;

  /* ------------------------ pure helpers -------------------------- */
  /* Round a numeric obs component for display; pass strings through. */
  function fmtNum(v) {
    if (typeof v !== 'number') return String(v);
    if (Number.isInteger(v)) return String(v);
    return (Math.round(v * 10000) / 10000).toString();
  }

  /* Turn an observation (scalar or vector) into DOM-free row specs:
   * one row per component with a normalized bar fraction (scaled by
   * the largest magnitude in the vector, so at least one row fills). */
  function obsRows(obs) {
    const arr = Array.isArray(obs) ? obs : [obs];
    const nums = arr.map(v => (typeof v === 'number' ? v : Number(v)));
    let maxAbs = 0;
    nums.forEach(v => { if (Number.isFinite(v) && Math.abs(v) > maxAbs) maxAbs = Math.abs(v); });
    if (maxAbs === 0) maxAbs = 1;
    return arr.map((v, i) => {
      const numeric = typeof v === 'number' && Number.isFinite(v);
      return {
        i, value: v, numeric,
        frac: numeric ? Math.abs(nums[i]) / maxAbs : 0,
        sign: numeric && nums[i] < 0 ? -1 : 1,
      };
    });
  }

  /* Build a box action vector: fill every dim with low[0] / 0 / high[0]. */
  function boxAction(actionSpace, which) {
    const shape = actionSpace.shape || [1];
    const n = shape.reduce((a, b) => a * b, 1) || 1;
    const lo = Array.isArray(actionSpace.low) ? actionSpace.low[0] : actionSpace.low;
    const hi = Array.isArray(actionSpace.high) ? actionSpace.high[0] : actionSpace.high;
    const val = which === 'low' ? lo : which === 'high' ? hi : 0;
    return new Array(n).fill(typeof val === 'number' ? val : 0);
  }

  /* Which highlight class a spiel log entry gets. */
  function logClass(entryPlayer, humanSeat) {
    return entryPlayer === humanSeat ? 'lab0' : 'lab1';
  }

  /* --------------------------- fetch ------------------------------ */
  /* Resolve with parsed JSON, or reject with {kind}: 'http' (server
   * replied with an error status) vs 'net' (server unreachable). */
  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(
      r => r.json().catch(() => ({})).then(d => {
        if (!r.ok) return Promise.reject({ kind: 'http', status: r.status, error: (d && d.error) || ('HTTP ' + r.status) });
        return d;
      }),
      () => Promise.reject({ kind: 'net' })
    );
  }

  const $ = sel => document.querySelector(sel);
  const alive = my => my === token && S;

  function showError(host, err) {
    if (err && err.kind === 'http') {
      host.innerHTML = '<h2>Live play</h2>' +
        '<p class="hint">The server rejected this: ' + esc(err.error) + '</p>';
    } else {
      host.innerHTML = '<h2>Live play <span class="h-sub">needs the Python backend</span></h2>' +
        '<p class="hint">Could not reach the server. Start it with ' +
        '<code>uv run python server/app.py</code> and open ' +
        '<code>http://localhost:8000</code>, then reopen this game.</p>';
    }
  }

  /* ============================ GYM ============================== */
  function mountGym(entry, host) {
    S = { kind: 'gym', entry, host, data: null, sid: null, auto: false };
    const my = token;
    host.innerHTML = '<h2>' + esc(entry.name) + ' <span class="h-sub">starting environment&hellip;</span></h2>';
    post('/api/env/new', { envId: entry.play.envId, seed: randSeed() })
      .then(d => { if (!alive(my)) return; S.data = d; S.sid = d.sid; renderGym(); })
      .catch(err => { if (alive(my)) showError(host, err); });
  }

  function gymStatusHTML(d) {
    return 'steps <b>' + d.steps + '</b> <span class="env-sep">&middot;</span> ' +
      'last reward <b>' + fmtNum(d.reward) + '</b> <span class="env-sep">&middot;</span> ' +
      'total return <b>' + fmtNum(d.total) + '</b>';
  }

  function obsVectorHTML(obs, obsSpace) {
    const rows = obsRows(obs).map(r => {
      const bar = r.numeric
        ? '<span class="obs-bar"><span class="obs-bar-fill' + (r.sign < 0 ? ' neg' : '') +
          '" style="width:' + (r.frac * 100).toFixed(1) + '%"></span></span>'
        : '';
      return '<div class="obs-row"><span class="obs-idx">[' + r.i + ']</span>' +
        '<span class="obs-val">' + esc(fmtNum(r.value)) + '</span>' + bar + '</div>';
    }).join('');
    return '<div class="obs-vec">' + rows + '</div>' +
      (obsSpace ? '<div class="obs-cap muted">obs space: ' + esc(obsSpace) + '</div>' : '');
  }

  function gymDoneBannerHTML(d) {
    const cls = d.total > 0 ? 'win' : d.total < 0 ? 'lose' : 'draw';
    const why = d.truncated ? 'truncated (time limit)' : 'terminated';
    return '<div class="play-banner ' + cls + '">Episode ' + why +
      ' &middot; return ' + fmtNum(d.total) + '</div>';
  }

  function renderGym() {
    const s = S;
    const d = s.data;
    const view = d.render != null && d.render !== ''
      ? '<pre class="env-render">' + esc(d.render) + '</pre>'
      : obsVectorHTML(d.obs, d.obsSpace);
    s.host.innerHTML =
      '<h2>' + esc(s.entry.name) + ' <span class="h-sub">live gymnasium env</span></h2>' +
      '<div class="mode-note">Step the env yourself with the action buttons, or flip ' +
      '<b>policy: random</b> to watch a random policy drive. Reset any time.</div>' +
      '<div class="env-status" id="env-status">' + gymStatusHTML(d) + '</div>' +
      '<div class="env-view">' + view + '</div>' +
      (d.done ? gymDoneBannerHTML(d) : '') +
      '<div class="move-btns env-actions" id="env-actions"></div>' +
      '<div class="play-actions env-controls" id="env-controls"></div>';

    fillGymActions();
    fillGymControls();
  }

  function mkBtn(cls, label, onClick, opts) {
    const b = document.createElement('button');
    b.className = cls;
    b.textContent = label;
    if (opts && opts.title) b.title = opts.title;
    if (opts && opts.disabled) b.disabled = true;
    b.addEventListener('click', onClick);
    return b;
  }

  function fillGymActions() {
    const s = S;
    const host = $('#env-actions');
    if (!host) return;
    host.innerHTML = '';
    const a = s.data.actionSpace;
    const done = s.data.done;
    if (a.type === 'discrete') {
      for (let i = 0; i < a.n; i++) {
        const name = (a.names && a.names[i]) || ('action ' + i);
        host.appendChild(mkBtn('move-btn', name, () => gymStep({ action: i }), { disabled: done }));
      }
    } else if (a.type === 'box') {
      [['low', 'low'], ['zero', 'zero'], ['high', 'high']].forEach(([key, label]) => {
        host.appendChild(mkBtn('move-btn', label,
          () => gymStep({ action: boxAction(a, key) }), { disabled: done }));
      });
    } else {
      host.appendChild(mkBtn('move-btn', 'sample action',
        () => gymStep({ policy: 'random' }), { disabled: done }));
    }
  }

  function fillGymControls() {
    const s = S;
    const host = $('#env-controls');
    if (!host) return;
    host.innerHTML = '';
    const done = s.data.done;
    host.appendChild(mkBtn('btn-sec', 'random step',
      () => gymStep({ policy: 'random' }), { disabled: done, title: 'apply one random action' }));
    const auto = mkBtn('btn-sec env-toggle' + (s.auto ? ' on' : ''),
      'policy: random ' + (s.auto ? '(on)' : '(off)'),
      toggleAuto, { disabled: done, title: 'let a random policy step ~250ms apart' });
    host.appendChild(auto);
    host.appendChild(mkBtn('btn-sec', 'reset', gymReset, { title: 'reset the environment' }));
  }

  function gymStep(body) {
    const s = S;
    if (!s || s.kind !== 'gym' || !s.sid || s.data.done) return;
    const my = token;
    post('/api/env/' + s.sid + '/step', body)
      .then(d => {
        if (!alive(my) || S !== s) return;
        s.data = d;
        if (d.done) s.auto = false;
        renderGym();
        if (s.auto && !d.done) scheduleAuto();
      })
      .catch(err => { if (alive(my)) { s.auto = false; showError(s.host, err); } });
  }

  function toggleAuto() {
    const s = S;
    if (!s || s.data.done) return;
    s.auto = !s.auto;
    fillGymControls();
    if (s.auto) scheduleAuto();
  }

  function scheduleAuto() {
    const s = S;
    const my = token;
    setTimeout(() => {
      if (!alive(my) || S !== s || !s.auto || s.data.done) return;
      gymStep({ policy: 'random' });
    }, 250);
  }

  function gymReset() {
    const s = S;
    if (!s || s.kind !== 'gym' || !s.sid) return;
    s.auto = false;
    const my = token;
    post('/api/env/' + s.sid + '/reset', { seed: randSeed() })
      .then(d => { if (!alive(my) || S !== s) return; s.data = d; renderGym(); })
      .catch(err => { if (alive(my)) showError(s.host, err); });
  }

  /* =========================== SPIEL ============================= */
  function mountSpiel(entry, host) {
    S = { kind: 'spiel', entry, host, data: null, sid: null, autoplaying: false };
    startSpiel();
  }

  function startSpiel() {
    const s = S;
    s.autoplaying = false;
    const my = token;
    s.host.innerHTML = '<h2>' + esc(s.entry.name) + ' <span class="h-sub">dealing&hellip;</span></h2>';
    post('/api/spiel/new', { game: s.entry.play.game, seed: randSeed() })
      .then(d => { if (!alive(my) || S !== s) return; s.data = d; s.sid = d.sid; renderSpiel(); })
      .catch(err => { if (alive(my)) showError(s.host, err); });
  }

  function spielLogHTML(log, humanSeat) {
    if (!log || !log.length) return '<div class="muted">no moves yet.</div>';
    return log.map(e => {
      const cls = logClass(e.p, humanSeat);
      const who = e.p === humanSeat ? 'you' : ('P' + e.p);
      return '<div class="log-line"><span class="' + cls + '">' + esc(who) + '</span> ' +
        esc(e.s) + '</div>';
    }).join('');
  }

  function spielReturnsHTML(d) {
    const parts = (d.returns || []).map((r, p) => {
      const cls = p === d.humanSeat ? 'lab0' : 'lab1';
      const who = p === d.humanSeat ? 'you' : ('P' + p);
      return '<span class="ret-cell"><span class="' + cls + '">' + who + '</span> ' + fmtNum(r) + '</span>';
    }).join('');
    const you = (d.returns || [])[d.humanSeat] || 0;
    const cls = you > 0 ? 'win' : you < 0 ? 'lose' : 'draw';
    return '<div class="play-banner ' + cls + '">Game over</div>' +
      '<div class="spiel-returns">' + parts + '</div>';
  }

  function renderSpiel() {
    const s = S;
    const d = s.data;
    const head = 'You are player <b class="lab0">' + d.humanSeat + '</b> of ' + d.players +
      ' <span class="h-sub">other seats: random bot</span>';
    s.host.innerHTML =
      '<h2>' + esc(s.entry.name) + ' <span class="h-sub">live open_spiel game</span></h2>' +
      '<div class="mode-note">' + head + '</div>' +
      (d.terminal ? spielReturnsHTML(d) : '') +
      '<pre class="env-render">' + esc(d.obs || '') + '</pre>' +
      (d.terminal ? '' : '<div class="legal-moves" id="spiel-legal"></div>') +
      '<div class="play-actions" id="spiel-controls"></div>' +
      '<h3>Move log</h3>' +
      '<div class="log-panel" id="spiel-log">' + spielLogHTML(d.log, d.humanSeat) + '</div>';

    fillSpielLegal();
    fillSpielControls();
  }

  function fillSpielLegal() {
    const s = S;
    const host = $('#spiel-legal');
    if (!host) return;
    host.innerHTML = '';
    const d = s.data;
    if (d.terminal || d.cur !== d.humanSeat) {
      host.innerHTML = '<span class="muted">waiting&hellip;</span>';
      return;
    }
    (d.legal || []).forEach(m => {
      host.appendChild(mkBtn('move-btn', m.s, () => spielAct({ action: m.a })));
    });
  }

  function fillSpielControls() {
    const s = S;
    const host = $('#spiel-controls');
    if (!host) return;
    host.innerHTML = '';
    const term = s.data.terminal;
    host.appendChild(mkBtn('btn-sec', 'random move',
      () => spielAct({ policy: 'random' }), { disabled: term, title: 'play a random legal move for you' }));
    host.appendChild(mkBtn('btn-sec', 'autoplay to end',
      startAutoplay, { disabled: term, title: 'random moves to the end of the game' }));
    host.appendChild(mkBtn('btn-sec', 'new game', startSpiel, { title: 'deal a fresh game' }));
  }

  function spielAct(body) {
    const s = S;
    if (!s || s.kind !== 'spiel' || !s.sid || s.data.terminal) return Promise.resolve();
    const my = token;
    return post('/api/spiel/' + s.sid + '/act', body)
      .then(d => { if (!alive(my) || S !== s) return; s.data = d; renderSpiel(); return d; })
      .catch(err => { if (alive(my)) { s.autoplaying = false; showError(s.host, err); } });
  }

  function startAutoplay() {
    const s = S;
    if (!s || s.data.terminal) return;
    s.autoplaying = true;
    autoplayStep(0);
  }

  function autoplayStep(count) {
    const s = S;
    const my = token;
    if (!alive(my) || S !== s || !s.autoplaying || s.data.terminal || count >= 300) {
      if (s) s.autoplaying = false;
      return;
    }
    spielAct({ policy: 'random' }).then(() => {
      setTimeout(() => autoplayStep(count + 1), 120);
    });
  }

  /* ========================== public ============================= */
  function mount(entry, host) {
    unmount();
    if (!entry || !entry.play || !host) return;
    token++;
    if (entry.play.kind === 'gym') mountGym(entry, host);
    else if (entry.play.kind === 'spiel') mountSpiel(entry, host);
  }

  function unmount() {
    token++;                 // orphan any pending timer / fetch callback
    if (S) S.auto = false;
    if (S) S.autoplaying = false;
    S = null;
  }

  return {
    mount, unmount,
    /* pure helpers, for tests */
    _pure: { fmtNum, obsRows, boxAction, logClass },
  };
})();
