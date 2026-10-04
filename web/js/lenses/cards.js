/* Cards lens view: build a strategy from rule cards, see which card decides
 * right now, and simulate the stack against a bot (POST /api/simulate).
 * Result schema: strategy_lab/lenses/cards.py. */

import { api } from '../api.js';
import { clear, h, local, pct } from '../dom.js';
import { icon } from '../icons.js';
import { lineChart, splitBar } from '../charts.js';
import { store } from '../store.js';
import { LensView } from './lens.js';

export default class CardsLens extends LensView {
  constructor(page, meta) {
    super(page, meta);
    this.stack = local.get(`lab.stack.${page.id}`, null) || [];
    this.simBot = null;
    this.simN = 100;
    this.sim = null;
  }

  requestOptions() { return { stack: this.stack }; }

  save() { local.set(`lab.stack.${this.page.id}`, this.stack); }

  setStack(ids) { this.stack = ids; this.save(); this.refresh(true); }

  render(r) {
    const cards = Object.fromEntries(r.cards.map((c) => [c.id, c]));
    const steps = Object.fromEntries((r.trace?.steps || []).map((s) => [s.card, s]));
    const b = this.body;

    // --- the stack
    const list = h('ol.stack-list');
    this.stack.forEach((cid, i) => {
      const c = cards[cid];
      if (!c) return;
      const decided = r.trace?.card === cid;
      list.append(h('li.stack-card', { class: `${c.kind}${decided ? ' decided' : ''}` },
        h('span.sc-kind', c.kind === 'avoid' ? 'AVOID' : 'PICK'),
        h('span.sc-body', h('strong', c.name), h('span.sc-now.small', steps[cid]?.result || '')),
        h('span.sc-tools',
          h('button.btn.ghost.icon-only.small', { title: 'Up', disabled: i === 0, onclick: () => this.move(i, -1) }, icon('chevron-down', { cls: 'flip' })),
          h('button.btn.ghost.icon-only.small', { title: 'Down', disabled: i === this.stack.length - 1, onclick: () => this.move(i, 1) }, icon('chevron-down')),
          h('button.btn.ghost.icon-only.small', { title: 'Remove', onclick: () => this.setStack(this.stack.filter((x) => x !== cid)) }, icon('close')))));
    });
    if (!this.stack.length) list.append(h('li.stack-empty', 'Empty stack: every move is random. Add cards below; the top card is read first.'));
    b.append(h('div.lens-card', h('div.upper.muted', 'Your stack'), list, this.decision(r)));

    // --- palette
    const pal = h('div.palette');
    for (const c of r.cards) {
      if (this.stack.includes(c.id)) continue;
      pal.append(h('button.palette-card', { class: c.kind, title: c.desc, onclick: () => this.setStack([...this.stack, c.id]) },
        h('span.sc-kind', c.kind === 'avoid' ? 'AVOID' : 'PICK'), h('strong', c.name), h('span.small.muted', c.desc)));
    }
    if (pal.children.length) b.append(h('div.lens-card', h('div.upper.muted', 'Card palette: click to add'), pal));

    // --- study bots
    const bots = r.bots.filter((x) => x.cards.length);
    if (bots.length) {
      b.append(h('div.lens-card', h('div.upper.muted', 'Study a bot: copy its stack'),
        h('div.row.wrap', bots.map((x) => h('button.chip', { onclick: () => this.setStack([...x.cards]) },
          stars(x.stars), x.name)))));
    }

    // --- simulate
    b.append(this.simPanel(r));
  }

  decision(r) {
    const t = r.trace;
    if (!t) return h('p.small.muted.decision', this.page.state?.humanTurn ? 'Add cards to see what your stack would play.' : 'Your stack speaks when it is your turn.');
    let text;
    if (t.reason === 'card') text = `plays ${t.label} because of "${(r.cards.find((c) => c.id === t.card) || {}).name}".`;
    else if (t.reason === 'forced') text = `has only one candidate left: ${t.label}.`;
    else text = 'has no opinion here: it would pick at random.';
    const canPlay = this.page.state?.humanTurn && t.action != null;
    return h('div.decision', h('span', icon('lightbulb'), ` Your stack ${text}`),
      canPlay ? h('button.btn.small', { onclick: () => this.page.act(t.action) }, 'Play it') : null);
  }

  simPanel() {
    const detail = this.page.detail;
    const bots = detail.bots;
    this.simBot ||= this.page.opponentBot() || bots[0]?.id;
    const panel = h('div.lens-card.sim',
      h('div.upper.muted', 'Simulate your stack'),
      h('div.row.wrap',
        h('label.field', h('span', 'Against'), h('select', { onchange: (e) => { this.simBot = e.target.value; } },
          bots.map((x) => h('option', { value: x.id, selected: x.id === this.simBot }, `${x.name} (${'*'.repeat(x.stars)})`)))),
        h('label.field', h('span', 'Games'), h('select', { onchange: (e) => { this.simN = parseInt(e.target.value, 10); } },
          [20, 100, 300].map((n) => h('option', { value: n, selected: n === this.simN }, String(n))))),
        h('button.btn.primary', { onclick: () => this.simulate() }, icon('fast'), 'Simulate')));
    this.simOut = h('div.sim-out');
    if (this.sim) this.drawSim(this.sim);
    panel.append(this.simOut);
    return panel;
  }

  async simulate() {
    clear(this.simOut);
    this.simOut.append(h('div.empty', 'Playing games...'));
    try {
      const res = await api.simulate({ game: this.page.id, params: this.page.sess.params,
        stack: this.stack, bot: this.simBot, n: this.simN, seed: Math.floor(Math.random() * 1e9) });
      this.sim = res;
      this.drawSim(res);
      await store.achieved(res.achieved);
    } catch (e) {
      clear(this.simOut);
      this.simOut.append(h('div.lens-error', e.message));
    }
  }

  drawSim(res) {
    clear(this.simOut);
    const s = res.stats;
    const losses = s.n - s.wins[0] - s.draws;
    let lead = 0;
    const momentum = s.games.map((g) => { lead += g.winner === 0 ? 1 : g.winner == null ? 0 : -1; return lead; });
    this.simOut.append(
      splitBar([
        { value: s.wins[0], color: 'var(--good)', label: 'Won' },
        { value: s.draws, color: 'var(--muted)', label: 'Draw' },
        { value: losses, color: 'var(--bad)', label: 'Lost' },
      ]),
      h('div.row.between.small', h('span', `${pct(s.wins[0] / s.n)} wins vs ${s.names[1]}`), h('span.muted', `${s.seconds}s`)),
      lineChart({ series: [{ values: momentum, color: 'var(--accent)', label: 'your lead (wins - losses)' }], height: 110, refLines: [{ y: 0 }] }),
      h('p.small.muted', `When your stack moved first it won ${s.firstMover[0].wins}/${s.firstMover[0].games}; second ${s.n - s.firstMover[0].games ? `${s.wins[0] - s.firstMover[0].wins}/${s.n - s.firstMover[0].games}` : '-'}.`),
    );
    if (res.insight) this.simOut.append(h('p.insight', icon('sparkle'), res.insight));
  }

  move(i, d) {
    const st = [...this.stack];
    [st[i], st[i + d]] = [st[i + d], st[i]];
    this.setStack(st);
  }
}

function stars(n) {
  return h('span.stars', Array.from({ length: n }, () => icon('star')));
}
