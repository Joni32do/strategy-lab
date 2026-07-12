/* ============================================================
 * Strategy Lab — the MDP registry.
 *
 * The card-stack lab quietly assumes a simple MDP: the state is
 * "whatever the board shows now", history forgotten. That is fine
 * for Tic-Tac-Toe and fatal for chess (castling rights, repetition),
 * skat (card counting IS the game) or tetris (the 7-bag piece
 * randomizer). So here the choice of MDP becomes an explicit,
 * inspectable, *changeable* thing:
 *
 *   an explorable game  = metadata (genre, backend engine, env id)
 *                       + SEVERAL candidate MDPs (state space,
 *                         action space, reward), each flagged
 *                         Markov / approx / not Markov,
 *                       + one line on where history bites.
 *
 * The UI renders this as a collapsed <details> panel: open it to
 * read the current formulation, tick a radio to switch state
 * spaces. The selection persists per game (localStorage).
 *
 * Backends are the vendored submodules — Gymnasium (single-agent
 * envs, e.g. ALE/Atari) and OpenSpiel (n-player games like chess
 * and skat). Browsing the catalog works fully offline; playing /
 * training against the real envs arrives with the Python backend.
 *
 * Everything except the two render helpers is DOM-free so node can
 * test it headlessly.
 * ============================================================ */
window.MDP = (function () {
  'use strict';

  /* ---------------- genres (the home-menu axis) ---------------- */
  const genres = [
    { id: 'classic', name: 'Classic & solved', desc: 'the playable card-stack lab games' },
    { id: 'board', name: 'Board', desc: 'perfect information, big trees' },
    { id: 'card', name: 'Card', desc: 'imperfect information — memory is strategy' },
    { id: 'atari', name: 'Atari / arcade', desc: 'Gymnasium ALE environments' },
    { id: 'control', name: 'Classic control', desc: 'the Gymnasium starter set' },
  ];

  /* ---------------- registry ---------------- */
  const games = [];

  /* entry = {
   *   id, name, icon, genre, blurb, players,
   *   backend: 'gymnasium' | 'open_spiel' | 'js',
   *   envId:   registry id of the real environment ('chess', 'ALE/Tetris-v5', ...),
   *   history: one line on where history bites in this game,
   *   playable: true if a card-stack lab game with the same id exists,
   *   play?:   how to play it against the server (js/env-play.js):
   *            { kind: 'gym', envId } | { kind: 'spiel', game } - absent
   *            means browse-only,
   *   mdps: [{ id, name, markov: true|false|'approx',
   *            state, stateSize?, actions, transition?, reward, note? }],
   *   defaultMdp?: id (else the first)
   * } */
  function register(entry) { games.push(entry); return entry; }
  function get(id) { return games.find(g => g.id === id); }

  /* ------------- selected-MDP persistence (node-safe) ------------- */
  const KEY = 'strategy-lab-mdp-v1';
  let mem = {};                       // fallback store outside the browser
  function readStore() {
    if (typeof localStorage === 'undefined') return mem;
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function writeStore(s) {
    mem = s;
    if (typeof localStorage === 'undefined') return;
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private mode */ }
  }
  function setSelected(gameId, mdpId) {
    const s = readStore(); s[gameId] = mdpId; writeStore(s);
  }
  function selectedMdp(gameId) {
    const e = get(gameId);
    if (!e) return null;
    const want = readStore()[gameId];
    if (want && e.mdps.some(v => v.id === want)) return want;
    return e.defaultMdp || e.mdps[0].id;
  }
  function variant(entry, mdpId) {
    return entry.mdps.find(v => v.id === mdpId) || entry.mdps[0];
  }

  /* ---------------- render helpers (DOM-free string builders) ------ */
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function markovBadge(m) {
    if (m === true) return '<span class="mdp-badge ok">Markov</span>';
    if (m === false) return '<span class="mdp-badge no">not Markov</span>';
    return '<span class="mdp-badge approx">approx. Markov</span>';
  }

  /* The collapsed, openable, changeable MDP panel.
   * opts: { open: bool, dataD: string (survives re-render bookkeeping) } */
  function panelHTML(entry, selectedId, opts) {
    opts = opts || {};
    const sel = variant(entry, selectedId);
    const choices = entry.mdps.map(v => `
      <label class="mdp-choice${v.id === sel.id ? ' sel' : ''}">
        <input type="radio" name="mdp-${entry.id}" value="${v.id}"${v.id === sel.id ? ' checked' : ''}>
        <span class="mc-name">${esc(v.name)}</span> ${markovBadge(v.markov)}
      </label>`).join('');
    return `
    <details class="mdp-spec"${opts.open ? ' open' : ''}${opts.dataD ? ` data-d="${opts.dataD}"` : ''}>
      <summary>MDP: <b>${esc(sel.name)}</b> ${markovBadge(sel.markov)}
        <span class="h-sub">open to inspect / change</span></summary>
      <div class="mdp-choices">${choices}</div>
      <dl class="rl-dl">
        <dt>State s</dt><dd>${esc(sel.state)}${sel.stateSize ? ` <span class="muted">(${esc(sel.stateSize)})</span>` : ''}</dd>
        <dt>Actions A(s)</dt><dd>${esc(sel.actions)}</dd>
        ${sel.transition ? `<dt>Transition</dt><dd>${esc(sel.transition)}</dd>` : ''}
        <dt>Reward</dt><dd>${esc(sel.reward)}</dd>
        ${sel.note ? `<dt>Why / cost</dt><dd>${esc(sel.note)}</dd>` : ''}
      </dl>
      ${entry.history ? `<p class="mdp-history"><b>Where history bites:</b> ${esc(entry.history)}</p>` : ''}
    </details>`;
  }

  /* Wire the radios after panelHTML has been inserted somewhere. */
  function bindPanel(rootEl, entry, onChange) {
    Array.from(rootEl.querySelectorAll(`input[name="mdp-${entry.id}"]`)).forEach(inp =>
      inp.addEventListener('change', () => {
        setSelected(entry.id, inp.value);
        if (onChange) onChange(inp.value);
      }));
  }

  return {
    genres, games, register, get,
    selectedMdp, setSelected, variant,
    panelHTML, bindPanel, markovBadge, esc,
  };
})();
