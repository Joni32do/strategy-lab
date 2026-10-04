/* The game page: play a game, watch bots, open lenses.
 *
 * The browser owns the session {game, params, seed, seats, log, sid}; the
 * server replays it on every request (strategy_lab/core/session.py). After
 * a human move, bots and chance are stepped one request at a time so you
 * can watch them; "skip" lets the server run them all at once.
 *
 * Layout: stage (status, scoreboard, board parts, action bar, controls,
 * move log) on the left, the dock (rules, goals, lenses) on the right. */

import { api } from '../api.js';
import { clear, h, local, prob, randomSeed, sleep, uid } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { go } from '../router.js';
import { skin } from '../skins/registry.js';
import { ensureViews, viewClass } from '../views/registry.js';
import { lensClass } from '../lenses/registry.js';
import { conceptName } from '../lenses/lens.js';
import { md } from '../text.js';
import { toast } from './shell.js';
import { openCheatsheet } from './cheatsheet.js';
import { confetti } from './celebrate.js';
import { tutorial } from './tutorial.js';
import { starRow } from './gallery.js';

const CHANCE = -1;

export class GamePage {
  async mount(el, params) {
    this.el = el;
    this.id = params.id;
    this.alive = true;
    this.views = [];
    this.lenses = {};
    this.overlay = null;
    this.busy = false;
    this.paused = false;
    this.steps = [];
    this.speed = 1;
    this.tab = local.get(`lab.tab.${this.id}`, 'rules');
    try {
      this.detail = await api.game(this.id);
    } catch (e) {
      el.append(h('div.page.narrow', h('h2', 'Game not found'), h('p', e.message), h('a.btn', { href: '#/' }, 'Back to the gallery')));
      return;
    }
    this.meta = store.gameMeta(this.id) || {};
    if (this.meta && this.meta.unlocked === false) { this.lockedScreen(); return; }
    this.build();
    this.offs = [
      store.on('reloaded', () => this.reloadRules()),
      store.on('skin', () => { this.views = []; if (this.state) this.render(this.state); }),
      store.on('profile', () => this.drawGoalsIfOpen()),
    ];
    this.keys = (e) => this.onKey(e);
    document.addEventListener('keydown', this.keys);
    if (params.replay) {
      await this.startReplay(params.replay);
    } else {
      const saved = local.get(this.key(), null);
      if (saved?.log && !saved.terminal) await this.resume(saved);
      else this.showSetup();
    }
    tutorial.game(this);
  }

  unmount() {
    this.alive = false;
    (this.offs || []).forEach((f) => f());
    document.removeEventListener('keydown', this.keys);
  }

  key() { return `lab.session.v1.${this.id}`; }

  lockedScreen() {
    this.el.append(h('div.page.narrow.locked-screen', icon('lock', { size: 40 }), h('h2', `${this.detail.name} is still locked`),
      h('p.muted', 'Finish the games before it in the gallery, or turn on Explorer mode in the settings.'),
      h('a.btn.primary', { href: '#/' }, 'Back to the gallery')));
  }

  /* ------------------------------------------------------------------ layout */
  build() {
    const d = this.detail;
    const color = this.meta.chapterColor || 'slate';
    this.root = h('div.page.game-page', { style: { '--cc': `var(--c-${color})` } });
    const lineage = h('div.lineage-mini', d.lineage.map((n, i) => [i ? h('span.sep', '\u{203A}') : null,
      h('code', { class: i === d.lineage.length - 1 ? 'me' : '' }, n)]));
    this.head = h('header.game-head',
      h('a.btn.ghost.small', { href: '#/' }, icon('arrow-left'), 'Gallery'),
      h('div.game-title', h('span.title-icon', icon(d.icon)),
        h('div', h('h1', d.name), h('div.row.wrap.small.muted', this.meta.chapterTitle ? h('span', this.meta.chapterTitle) : null, lineage))),
      h('div.game-tools',
        h('button.btn.small', { onclick: () => this.showSetup(), 'data-tour': 'new-game' }, icon('reset'), 'New game'),
        h('button.btn.small.ghost', { onclick: () => this.openTab('rules') }, icon('book'), 'Rules'),
        h('button.btn.small.ghost', { onclick: () => openCheatsheet() }, icon('cheatsheet'), 'Cheatsheet')));
    this.statusEl = h('div.status-line');
    this.scoreEl = h('div.scoreboard');
    this.boardEl = h('div.board-area', { 'data-tour': 'board' });
    this.barEl = h('div.actionbar');
    this.controlsEl = h('div.controls');
    this.bannerEl = h('div.end-banner.hidden');
    this.logEl = h('ol.movelog');
    this.setupEl = h('div.setup.hidden');
    this.notice = h('div.notice.hidden');
    this.stage = h('section.stage',
      this.notice, this.statusEl, this.scoreEl,
      h('div.board-wrap', this.boardEl, this.bannerEl, this.setupEl),
      this.barEl, this.controlsEl,
      h('details.log-box', { open: local.get('lab.logOpen', false), ontoggle: (e) => local.set('lab.logOpen', e.target.open) },
        h('summary', icon('history'), 'Move log'), this.logEl));
    this.tabsEl = h('nav.dock-tabs', { 'data-tour': 'lenses' });
    this.panelEl = h('div.dock-panel');
    this.dock = h('aside.dock', this.tabsEl, this.panelEl);
    this.root.append(this.head, h('div.game-grid', this.stage, this.dock));
    this.el.append(this.root);
    this.drawTabs();
  }

  /* ------------------------------------------------------------------- setup */
  showSetup() {
    const d = this.detail;
    const prev = local.get(this.key(), null) || {};
    let bot = prev.bot && d.bots.some((b) => b.id === prev.bot) ? prev.bot : (d.bots.find((b) => b.stars === 2) || d.bots[0])?.id;
    let seat = prev.seat ?? 0;
    let watch = prev.watch ?? !d.playableByHuman;
    const params = { ...d.values, ...(prev.params || {}) };
    const box = h('div.setup-card');
    const redraw = () => {
      clear(box);
      box.append(h('h2', d.playableByHuman ? 'Set up a match' : 'Set up the table'),
        h('p.muted', d.tagline));
      if (d.bots.length && d.players > 1) {
        box.append(h('div.upper.muted', watch ? 'Bots at the table' : (d.players > 2 ? 'Your opponents' : 'Your opponent')),
          h('div.personas', d.bots.map((b) => h('button.persona', {
            class: b.id === bot ? 'on' : '', onclick: () => { bot = b.id; redraw(); },
          }, h('span.persona-icon', icon(b.icon || 'bot')), h('strong', b.name), starRow(b.stars, 4), h('span.small.muted', b.desc)))));
      }
      if (d.players > 1 && d.playableByHuman && !watch) {
        box.append(h('div.upper.muted', 'Your seat'), h('div.segmented', d.seats.map((name, i) =>
          h('button', { class: i === seat ? 'on' : '', onclick: () => { seat = i; redraw(); } },
            name, i === 0 && !d.stochastic ? h('span.small.muted', ' (moves first)') : null))));
      }
      if (d.params.length) {
        const form = h('div.params');
        for (const p of d.params) form.append(paramInput(p, params));
        box.append(h('div.upper.muted', 'Variant'), form);
      }
      if (d.playableByHuman && d.players > 1) {
        box.append(h('label.toggle', h('input', { type: 'checkbox', checked: watch, onchange: (e) => { watch = e.target.checked; redraw(); } }),
          'Only watch: bots play every seat'));
      }
      box.append(h('div.row.end',
        this.state ? h('button.btn.ghost', { onclick: () => this.hideSetup() }, 'Cancel') : h('a.btn.ghost', { href: '#/' }, 'Back'),
        h('button.btn.primary.big', { onclick: () => this.start({ bot, seat, watch, params }), 'data-tour': 'start' },
          icon('play'), watch ? 'Watch' : 'Play')));
    };
    redraw();
    clear(this.setupEl).append(box);
    this.setupEl.classList.remove('hidden');
    this.boardEl.classList.add('dimmed');
  }

  hideSetup() {
    this.setupEl.classList.add('hidden');
    this.boardEl.classList.remove('dimmed');
  }

  async start({ bot, seat, watch, params }) {
    const n = this.detail.players;
    const seats = [];
    for (let i = 0; i < n; i++) {
      seats.push(!watch && i === seat ? { kind: 'human' } : { kind: 'bot', bot });
    }
    this.sess = { game: this.id, params, seed: randomSeed(), seats, log: [], sid: uid(), bot, seat, watch };
    this.steps = [];
    this.paused = false;
    this.replay = null;
    this.hideSetup();
    this.bannerEl.classList.add('hidden');
    await this.request({ mode: 'none' }, true);
    this.runBots();
  }

  async resume(saved) {
    this.sess = { ...saved };
    await this.request({ mode: 'none' }, true);
    if (this.state?.replayError) {
      toast(`The rules changed since this game was saved: ${this.state.replayError}. Continuing from there.`, { tone: 'warn', timeout: 7000 });
    }
    this.runBots();
  }

  /* ------------------------------------------------------------------ server */
  body() {
    const s = this.sess;
    return { game: s.game, params: s.params, seed: s.seed, seats: s.seats, log: s.log, sid: s.sid };
  }

  async request(extra = {}, full = false) {
    const since = full ? 0 : this.steps.length;
    let res;
    try {
      res = await api.play({ ...this.body(), since, record: !this.replay, ...extra });
    } catch (e) {
      toast(e.message, { tone: 'bad' });
      return null;
    }
    if (!this.alive) return null;
    if (res.error) toast(res.error, { tone: 'warn' });
    if (full || res.count < this.steps.length || extra.undo) this.steps = res.steps;
    else this.steps = this.steps.concat(res.steps.filter((st) => st.i >= this.steps.length));
    this.sess.log = res.log;
    this.state = res;
    if (!this.replay) {
      local.set(this.key(), { ...this.sess, terminal: res.terminal });
    }
    await this.render(res);
    if (res.achieved) store.achieved(res.achieved);
    return res;
  }

  async act(action) {
    if (this.busy || !this.state?.humanTurn || this.replay) return;
    this.busy = true;
    try {
      const res = await this.request({ action, mode: 'none' });
      if (res && !res.error) await this.runBots();
    } finally {
      this.busy = false;
      this.drawControls();
    }
  }

  async runBots() {
    if (this.running) return;
    this.running = true;
    try {
      let n = 0;
      while (this.alive && this.state && !this.state.terminal && !this.state.humanTurn && !this.paused && !this.replay) {
        await sleep(this.delay(this.state.toMove === CHANCE, n));
        if (!this.alive || this.paused) break;
        const res = await this.request({ mode: 'step' });
        if (!res) break;
        n += 1;
      }
    } finally {
      this.running = false;
      this.drawControls();
    }
  }

  delay(chance, n) {
    const base = chance ? 260 : 520;
    const ff = n > 30 ? 0.15 : n > 10 ? 0.5 : 1;
    return (base * ff) / (this.speed || 1);
  }

  async skip() {
    this.paused = false;
    await this.request({ mode: 'play' });
  }

  async undo() {
    if (this.busy) return;
    this.busy = true;
    try {
      this.bannerEl.classList.add('hidden');
      await this.request({ undo: true, mode: 'none' }, true);
    } finally {
      this.busy = false;
    }
  }

  async runLens(id, options) {
    const res = await api.lens(id, { ...this.body(), options, sid: this.sess.sid, record: !this.replay });
    if (res.achieved) store.achieved(res.achieved);
    return res.result;
  }

  opponentBot() { return this.sess?.bot || null; }

  /* ------------------------------------------------------------------ render */
  async render(res) {
    const scene = res.scene || { parts: [] };
    const parts = scene.parts || [];
    await ensureViews(parts.map((p) => p.view));
    const sk = skin();
    const same = this.views.length === parts.length
      && this.views.every((v, i) => v.constructor === viewClass(parts[i].view, sk));
    if (!same) {
      clear(this.boardEl);
      const ctx = {
        onAction: (a) => this.act(a),
        interactive: () => Boolean(this.state?.humanTurn) && !this.busy && !this.replay,
        names: this.seatNames(),
        viewer: res.viewer,
      };
      this.views = parts.map((p) => new (viewClass(p.view, sk))(ctx));
      this.views.forEach((v) => this.boardEl.append(v.el));
    }
    this.views.forEach((v) => { v.ctx.names = this.seatNames(); v.ctx.viewer = res.viewer; });
    parts.forEach((p, i) => this.views[i].update(p));
    this.boardEl.classList.toggle('split', scene.layout === 'split');
    this.boardEl.classList.toggle('interactive', Boolean(res.humanTurn) && !this.replay);
    this.drawStatus(res);
    this.drawScore(res, scene);
    this.drawBar(res);
    this.drawControls();
    this.drawLog();
    this.applyOverlay();
    if (res.terminal && !this.replay) this.drawBanner(res);
    else this.bannerEl.classList.add('hidden');
    if (res.humanTurn || res.terminal || this.paused || !this.hasHuman()) this.refreshLens();
  }

  seatNames() {
    const d = this.detail;
    const seats = this.sess?.seats || [];
    return seats.map((s, i) => {
      if (s.kind === 'human') return seats.filter((x) => x.kind === 'human').length > 1 ? `You (${d.seats[i]})` : 'You';
      const bot = d.bots.find((b) => b.id === s.bot);
      const base = bot ? bot.name : 'Bot';
      return seats.filter((x) => x.kind === 'bot' && x.bot === s.bot).length > 1 ? `${base} ${i + 1}` : base;
    });
  }

  hasHuman() { return (this.sess?.seats || []).some((s) => s.kind === 'human'); }

  drawStatus(res) {
    let text = res.status;
    if (!text) {
      if (res.terminal) text = 'Game over';
      else if (res.humanTurn) text = 'Your move';
      else if (res.toMove === CHANCE) text = 'Rolling...';
      else text = `${this.seatNames()[res.toMove] || 'Bot'} is thinking...`;
    }
    clear(this.statusEl).append(
      h('span.turn-dot', { class: res.humanTurn ? 'you' : res.terminal ? 'over' : 'wait' }),
      h('span.status-text', text));
    if (res.humanTurn) this.statusEl.append(h('span.chip.tiny.on', 'your turn'));
  }

  drawScore(res, scene) {
    const names = this.seatNames();
    // A game's own scoreboard keeps its scores and sub-lines, but the page
    // knows who sits where (You, Careful Carla, ...).
    const rows = scene.players ? scene.players.map((p, i) => ({ ...p, name: names[p.owner ?? i] ?? p.name }))
      : names.map((n, i) => ({
      name: n,
      sub: this.detail.seats[i] && this.detail.seats[i] !== n ? this.detail.seats[i] : '',
      score: res.terminal ? res.returns[i] : null,
      active: res.toMove === i,
      owner: i,
    }));
    clear(this.scoreEl).append(...rows.map((p, i) => h('div.score', {
      class: `${p.active ? 'active' : ''}${(this.sess?.seats?.[p.owner ?? i]?.kind === 'human') ? ' me' : ''}`,
      style: { '--pc': `var(--p${(p.owner ?? i) % 6})` },
    }, h('span.score-dot'), h('div.score-name', h('strong', p.name), p.sub ? h('span.small.muted', p.sub) : null),
    p.score != null ? h('span.score-val.num', typeof p.score === 'number' && !Number.isInteger(p.score) ? p.score.toFixed(1) : String(p.score)) : null)));
  }

  drawBar(res) {
    clear(this.barEl);
    if (!res.humanTurn || this.replay) { this.barEl.classList.add('hidden'); return; }
    const onBoard = new Set([...this.boardEl.querySelectorAll('[data-action]')].map((e) => e.dataset.action));
    const rest = res.legal.filter((l) => !onBoard.has(JSON.stringify(l.a)));
    if (!rest.length) { this.barEl.classList.add('hidden'); return; }
    this.barEl.classList.remove('hidden');
    const many = rest.length > 18;
    const chips = rest.map((l, i) => {
      const b = h('button.move', { dataset: { action: JSON.stringify(l.a) }, onclick: () => this.act(l.a) },
        i < 9 && !many ? h('span.kbd', String(i + 1)) : null, l.label);
      return b;
    });
    this.barEl.append(h('span.upper.muted', onBoard.size ? 'Other moves' : 'Moves'), h('div.moves', { class: many ? 'many' : '' }, chips));
  }

  drawControls() {
    clear(this.controlsEl);
    if (!this.state || this.replay) return;
    const res = this.state;
    const human = this.hasHuman();
    const canUndo = human && this.steps.some((st) => this.sess.seats[st.p]?.kind === 'human');
    const btns = [];
    if (human) {
      btns.push(h('button.btn.small.ghost', { disabled: !canUndo || this.busy, onclick: () => this.undo(), title: 'Undo (u)' }, icon('undo'), 'Undo'));
    }
    if (!res.terminal && !res.humanTurn) {
      if (!human || this.paused) {
        btns.push(h('button.btn.small', { onclick: () => { this.paused = !this.paused; this.drawControls(); if (!this.paused) this.runBots(); } },
          icon(this.paused ? 'play' : 'pause'), this.paused ? 'Play' : 'Pause'));
        btns.push(h('button.btn.small.ghost', { onclick: () => this.request({ mode: 'step' }) }, icon('step'), 'Step'));
      } else {
        btns.push(h('button.btn.small.ghost', { onclick: () => { this.paused = true; this.drawControls(); } }, icon('pause'), 'Pause'));
      }
      btns.push(h('button.btn.small.ghost', { onclick: () => this.skip(), title: 'Let the bots finish their moves now' }, icon('skip'), human ? 'Skip to my turn' : 'Skip to the end'));
    }
    const speed = h('label.speed.small.muted', 'Speed',
      h('input', { type: 'range', min: 0.5, max: 4, step: 0.5, value: this.speed, oninput: (e) => { this.speed = parseFloat(e.target.value); } }));
    this.controlsEl.append(h('div.row.wrap', btns), speed);
  }

  drawLog() {
    const names = this.seatNames();
    const items = this.steps.slice(-80).reverse().map((st) => {
      const who = st.p === CHANCE ? 'Chance' : names[st.p] || `Seat ${st.p + 1}`;
      return h('li', { class: st.p === CHANCE ? 'chance' : '', style: { '--pc': st.p >= 0 ? `var(--p${st.p % 6})` : 'var(--muted)' } },
        h('span.log-who', who), h('span.log-text', st.text),
        st.chance?.prob != null ? h('span.chip.tiny', { title: 'probability of this outcome' }, `p = ${prob(st.chance.prob)}`) : null);
    });
    clear(this.logEl).append(...items);
  }

  drawBanner(res) {
    const out = res.outcome;
    const human = this.hasHuman();
    const title = !human ? 'Game over' : out === 'win' ? 'You win!' : out === 'draw' ? 'A draw' : 'You lose';
    const sub = !human ? '' : out === 'win' ? 'Nicely played.' : out === 'draw' ? 'Nobody blinked.' : 'The lenses can show you why.';
    const next = store.nextGame();
    const scores = this.seatNames().map((n, i) => h('span.chip', { style: { '--pc': `var(--p${i % 6})` } }, h('span.score-dot'), `${n}: ${fmtNum(res.returns[i])}`));
    clear(this.bannerEl).append(h('div.banner-card', { class: `out-${out || 'over'}` },
      h('div.banner-icon', icon(out === 'win' ? 'trophy' : out === 'draw' ? 'scale' : out === 'loss' ? 'brain' : 'flag', { size: 34 })),
      h('h2', title), sub ? h('p.muted', sub) : null,
      h('div.row.wrap.center', scores),
      h('div.row.wrap.center',
        h('button.btn.primary', { onclick: () => this.start({ ...this.sess, watch: this.sess.watch }) }, icon('reset'), 'Play again'),
        h('button.btn', { onclick: () => this.showSetup() }, icon('sliders'), 'Change setup'),
        h('button.btn.ghost', { onclick: () => { this.bannerEl.classList.add('hidden'); } }, icon('eye'), 'Look at the board'),
        next && next.id !== this.id ? h('button.btn', { onclick: () => go(`/game/${next.id}`) }, `Next: ${next.name}`, icon('arrow-right')) : null)));
    this.bannerEl.classList.remove('hidden');
    if (out === 'win' && !this.celebrated) { this.celebrated = this.sess.sid; confetti(); }
  }

  /* -------------------------------------------------------------------- dock */
  drawTabs() {
    const d = this.detail;
    const tabs = [{ id: 'rules', title: 'Rules', icon: 'book' }, { id: 'goals', title: 'Goals', icon: 'trophy' },
      ...d.lenses.map((l) => ({ id: l.id, title: l.title, icon: l.icon, lens: l }))];
    if (!tabs.some((t) => t.id === this.tab)) this.tab = 'rules';
    clear(this.tabsEl).append(...tabs.map((t) => h('button.tab', {
      class: t.id === this.tab ? 'on' : '', dataset: { tab: t.id }, onclick: () => this.openTab(t.id), title: t.lens?.blurb || t.title,
    }, icon(t.icon), h('span', t.title))));
    this.openTab(this.tab, true);
  }

  async openTab(id, force = false) {
    if (this.tab === id && !force) return;
    if (this.lenses[this.tab] && this.tab !== id) this.lenses[this.tab].unmount();
    this.tab = id;
    local.set(`lab.tab.${this.id}`, id);
    for (const b of this.tabsEl.children) b.classList.toggle('on', b.dataset.tab === id);
    clear(this.panelEl);
    if (id === 'rules') { this.panelEl.append(this.rulesPanel()); this.setOverlay(null); return; }
    if (id === 'goals') { this.panelEl.append(this.goalsPanel()); this.setOverlay(null); return; }
    const meta = this.detail.lenses.find((l) => l.id === id);
    if (!meta) return;
    if (!this.lenses[id]) {
      const Cls = await lensClass(id);
      this.lenses[id] = new Cls(this, meta);
      this.lenses[id].mount();
    }
    this.panelEl.append(this.lenses[id].el);
    if (this.state) this.lenses[id].refresh();
  }

  refreshLens() {
    const lens = this.lenses[this.tab];
    if (lens && this.state) lens.positionChanged();
  }

  setOverlay(ov) { this.overlay = ov; this.applyOverlay(); }

  applyOverlay() {
    for (const v of this.views) v.annotate(this.overlay);
    for (const b of this.barEl.querySelectorAll('.move')) {
      b.querySelector('.ov')?.remove();
      const o = this.overlay?.actions?.[String(JSON.parse(b.dataset.action))];
      if (o) b.append(h(`span.ov.tone-${o.tone || 'neutral'}`, o.text ?? ''));
    }
  }

  rulesPanel() {
    const d = this.detail;
    const rb = d.rulebook;
    const box = h('section.lens.rules');
    box.append(h('header.lens-head', h('div.lens-title', icon('book'), h('h3', 'How to play')), rb ? h('p.lens-blurb', rb.summary) : null));
    if (rb) {
      box.append(h('ol.rule-steps', rb.steps.map((s) => h('li', h('strong', s.title), md(s.text)))));
      if (rb.extra.length) {
        box.append(h('details.rule-extra', h('summary', 'Details and variations'),
          h('ul', rb.extra.map((s) => h('li', h('strong', s.title), md(s.text))))));
      }
      if (rb.source) box.append(h('p.small', icon('book'), ' Official rules: ', h('a', { href: rb.source, target: '_blank', rel: 'noopener' }, rb.source)));
    } else {
      box.append(h('div.empty', 'No rulebook yet.'));
    }
    const fam = d.family;
    box.append(h('div.lens-card', h('div.upper.muted', 'Family'),
      h('p.small', h('strong', fam.name), fam.blurb ? ` \u{2014} ${fam.blurb}` : ''),
      h('p.tiny.muted', `Built as ${d.lineage.join(' \u{203A} ')}. Games in the same family share rules and rule cards.`)));
    return box;
  }

  goalsPanel() {
    const d = this.detail;
    const earned = new Set(store.progress?.stars?.[this.id] || d.earned || []);
    const learned = new Set(store.progress?.concepts || []);
    const box = h('section.lens.goals');
    box.append(h('header.lens-head', h('div.lens-title', icon('trophy'), h('h3', 'Goals')),
      h('p.lens-blurb', 'Challenges earn stars. Finishing a game adds its concept cards to your cheatsheet.')));
    box.append(h('ul.challenges', d.challenges.map((c) => h('li', { class: earned.has(c.id) ? 'done' : '' },
      icon(earned.has(c.id) ? 'badge' : 'target'), h('span', c.title), starRow(c.stars, c.stars)))));
    box.append(h('div.upper.muted', 'Concepts in this game'),
      h('div.row.wrap', d.concepts.map((c) => h('button.chip', { class: learned.has(c) ? 'on' : '', onclick: () => openCheatsheet(c) },
        icon(learned.has(c) ? 'check' : 'lock'), conceptName(c)))));
    const st = d.stats;
    if (st) {
      box.append(h('div.lens-card', h('div.upper.muted', 'Your record'),
        h('div.stat-row', h('div.stat', h('span.stat-label', 'Played'), h('span.stat-value.num', String(st.played))),
          h('div.stat', h('span.stat-label', 'Won'), h('span.stat-value.num', String(st.win))),
          h('div.stat', h('span.stat-label', 'Draw'), h('span.stat-value.num', String(st.draw))),
          h('div.stat', h('span.stat-label', 'Lost'), h('span.stat-value.num', String(st.loss))))));
    }
    return box;
  }

  drawGoalsIfOpen() {
    if (this.tab === 'goals' && this.panelEl) { clear(this.panelEl).append(this.goalsPanel()); }
  }

  openConcept(id) { openCheatsheet(id); }

  /* ------------------------------------------------------------------- dev */
  async reloadRules() {
    if (!this.sess || !this.alive) return;
    try {
      this.detail = await api.game(this.id);
    } catch (e) {
      this.showNotice(`The game failed to load after your edit: ${e.message}`);
      return;
    }
    this.lenses = {};
    this.drawTabs();
    this.views = [];
    const before = this.sess.log.length;
    const res = await this.request({ mode: 'none' }, true);
    if (!res) return;
    if (res.replayError) {
      this.showNotice(`Rules changed: ${res.replayError}. The game continues from move ${res.count}.`);
    } else {
      this.hideNotice();
      toast(`Reloaded the rules and replayed ${before} steps.`, { icon: 'bolt', timeout: 2500 });
    }
    this.runBots();
  }

  showNotice(text) {
    clear(this.notice).append(icon('wrench'), h('span', text), h('button.btn.small.ghost', { onclick: () => this.hideNotice() }, 'OK'));
    this.notice.classList.remove('hidden');
  }

  hideNotice() { this.notice.classList.add('hidden'); }

  /* ----------------------------------------------------------------- replay */
  async startReplay(sid) {
    const { games } = await api.history({ game: this.id, logs: 1, limit: 500 });
    const ev = games.find((g) => g.id === sid);
    if (!ev) { toast('That game is not in your history any more.', { tone: 'warn' }); this.showSetup(); return; }
    const n = this.detail.players;
    const bots = [...(ev.bots || [])];
    const seats = Array.from({ length: n }, (_, i) => (i === ev.seat ? { kind: 'human' } : { kind: 'bot', bot: bots.shift() || 'random' }));
    this.replay = { log: ev.log, at: ev.log.length };
    this.sess = { game: this.id, params: ev.params, seed: ev.seed, seats, log: ev.log, sid: `replay-${sid}` };
    const slider = h('input', { type: 'range', min: 0, max: ev.log.length, value: ev.log.length });
    const label = h('span.num.small', `${ev.log.length}/${ev.log.length}`);
    const seek = async (i) => {
      this.replay.at = i;
      label.textContent = `${i}/${ev.log.length}`;
      this.sess.log = ev.log.slice(0, i);
      await this.request({ mode: 'none' }, true);
    };
    slider.addEventListener('input', () => seek(parseInt(slider.value, 10)));
    this.stage.prepend(h('div.replay-bar', icon('history'), h('strong', 'Replay'),
      h('span.small.muted', `${ev.outcome} vs ${this.seatNames().filter((x) => x !== 'You').join(', ')}`),
      h('button.btn.small.ghost', { onclick: () => seek(Math.max(0, this.replay.at - 1)).then(() => { slider.value = this.replay.at; }) }, icon('arrow-left')),
      slider,
      h('button.btn.small.ghost', { onclick: () => seek(Math.min(ev.log.length, this.replay.at + 1)).then(() => { slider.value = this.replay.at; }) }, icon('arrow-right')),
      label,
      h('button.btn.small', { onclick: () => { go(`/game/${this.id}`); } }, 'Leave replay')));
    await seek(ev.log.length);
  }

  /* --------------------------------------------------------------- keyboard */
  onKey(e) {
    if (e.target.closest('input, select, textarea')) return;
    if (e.key === 'u' && this.hasHuman()) this.undo();
    else if (e.key === 'n') this.showSetup();
    else if (/^[1-9]$/.test(e.key)) {
      const b = this.barEl.querySelectorAll('.move')[parseInt(e.key, 10) - 1];
      if (b) b.click();
    }
  }
}

function paramInput(p, values) {
  const set = (v) => { values[p.name] = v; };
  let input;
  if (p.type === 'bool') {
    input = h('input', { type: 'checkbox', checked: Boolean(values[p.name]), onchange: (e) => set(e.target.checked) });
    return h('label.toggle', input, p.label, p.help ? h('span.small.muted', ` ${p.help}`) : null);
  }
  if (p.choices?.length) {
    input = h('select', { onchange: (e) => set(p.type === 'int' ? parseInt(e.target.value, 10) : p.type === 'float' ? parseFloat(e.target.value) : e.target.value) },
      p.choices.map((c) => h('option', { value: c, selected: c === values[p.name] }, String(c))));
  } else if (p.type === 'int' || p.type === 'float') {
    input = h('input', { type: 'number', value: values[p.name], min: p.min, max: p.max, step: p.type === 'int' ? 1 : 0.01,
      onchange: (e) => set(p.type === 'int' ? parseInt(e.target.value, 10) : parseFloat(e.target.value)) });
  } else {
    input = h('input', { type: 'text', value: values[p.name], onchange: (e) => set(e.target.value) });
  }
  return h('label.field', h('span', p.label), input, p.help ? h('span.hint', p.help) : null);
}

function fmtNum(x) {
  if (x == null) return '-';
  return Number.isInteger(x) ? String(x) : x.toFixed(1);
}
