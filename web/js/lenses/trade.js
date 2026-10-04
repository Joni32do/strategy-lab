/* Trading lens view (Catan): how strong is each player, how much weight does
 * a rival's gain get (the lambda curve), how would the rule judge the offer
 * on the table, and what happened in recent trades.
 * Result schema: strategy_lab/lenses/trade.py. */

import { clear, h, fmt } from '../dom.js';
import { lineChart } from '../charts.js';
import { LensView } from './lens.js';

const RES = ['wood', 'brick', 'sheep', 'wheat', 'ore'];
const GROUPS = [
  ['Strength metric', ['vp', 'production', 'expansion', 'prod_norm', 'expansion_norm', 'block_weight']],
  ['Trade rule', ['lam_max', 'lam_steepness', 'lam_midpoint', 'veto_vp_margin', 'margin', 'premium_per_vp',
    'scarcity_weight', 'need_weight', 'base_value']],
];
const TERMS = [['vpTerm', 'vp', 'victory points', 'var(--c-amber)'],
  ['productionTerm', 'production', 'production', 'var(--c-teal)'],
  ['reachTerm', 'expansion', 'room to expand', 'var(--c-violet)']];
// lineChart geometry (see charts.js): viewBox 320 x height, padding l34 r8 t8 b12.
const CH = { w: 320, h: 150, l: 34, r: 8, t: 8, b: 12 };

const cards = (freq) => freq.map((n, i) => (n ? `${n} ${RES[i]}` : null)).filter(Boolean).join(', ') || 'nothing';

export default class TradeLens extends LensView {
  drawOptions() {
    clear(this.optsEl);
    const byName = Object.fromEntries((this.meta.options || []).map((o) => [o.name, o]));
    for (const [title, names] of GROUPS) {
      this.optsEl.append(h('details.lens-knobs',
        h('summary', title),
        h('div.lens-options', names.filter((n) => byName[n]).map((n) => this.optionInput(byName[n])))));
    }
    if (byName.history) this.optsEl.append(this.optionInput(byName.history));
  }

  render(r) {
    const b = this.body;
    if (!r.players?.length) { b.append(h('div.empty', 'The board is not dealt yet.')); return; }
    b.append(this.strengthCard(r), this.curveCard(r));
    if (r.current) b.append(this.currentCard(r));
    b.append(this.decisionsCard(r));
  }

  strengthCard(r) {
    const rows = r.players.map((p) => {
      const segs = TERMS.map(([key, opt, label, color]) => {
        const w = (this.options[opt] ?? 0) * p[key];
        return h('span.tl-seg', { style: { width: `${Math.min(100, w * 100)}%`, background: color }, title: `${label}: ${fmt(w)}` });
      });
      return h('div.tl-player',
        h('span.tl-name', h('i', { style: { background: `var(--p${p.seat % 6})` } }), p.name),
        h('span.tl-track', segs),
        h('span.tl-value.num', fmt(p.strength)),
        h('span.tl-sub', `${p.vp} VP, ${fmt(p.production, 1)} pips, ${p.buildable} spots`));
    });
    return h('div.lens-card',
      h('div.upper.muted', 'Position strength'),
      h('div.tl-players', rows),
      h('div.legend', TERMS.map(([, , label, color]) => h('span.legend-item', h('i', { style: { background: color } }), label))),
      h('p.tiny.muted', 'Strength = VP weight x points + production weight x pips + expansion weight x room. '
        + 'The same function for every seat, so equal positions get equal treatment.'));
  }

  curveCard(r) {
    const c = r.curve;
    const hi = Math.max(0.5, c.lamMax);
    const chart = lineChart({
      series: [{ values: c.points.map((p) => p.lambda), color: 'var(--accent)' }],
      height: CH.h, yMin: 0, yMax: hi, xLabel: 'rival strength', yLabel: 'lambda: weight on the rival\'s gain',
      refLines: [{ y: c.lamMax / 2, label: 'half' }],
    });
    const box = h('div.tl-curve-plot');
    const plot = chart.querySelector('svg');
    plot.replaceWith(box);
    box.append(plot);
    const bottom = CH.b + 12; // chart adds a 24px bottom pad when it has an x label
    for (const m of r.markers) {
      const x = (CH.l + m.strength * (CH.w - CH.l - CH.r)) / CH.w;
      const y = (CH.t + (1 - m.lambda / hi) * (CH.h - CH.t - bottom)) / CH.h;
      box.append(h('span.tl-marker', {
        class: m.vetoed ? 'vetoed' : '',
        style: { left: `${x * 100}%`, top: `${y * 100}%`, background: `var(--p${m.seat % 6})` },
        title: `${m.name}: strength ${fmt(m.strength)}, lambda ${fmt(m.lambda)}${m.vetoed ? ' (veto)' : ''}`,
      }, m.name.slice(0, 1)));
    }
    return h('div.lens-card',
      h('div.upper.muted', `The trade coefficient, seen from ${r.players[r.perspective]?.name ?? 'the mover'}`),
      chart,
      h('p.small', 'A deal counts ', h('b', 'my gain \u{2212} lambda \u{D7} their gain'),
        `. It is accepted if that beats ${fmt(r.rule.margin)} plus ${fmt(r.rule.premiumPerVp)} per VP the partner leads. `,
        `Within ${c.vetoVpMargin} VP of ${c.vpsToWin} the answer is always no.`),
      r.markers.some((m) => m.vetoed) ? h('p.tiny.tl-veto', 'Vetoed now: '
        + r.markers.filter((m) => m.vetoed).map((m) => m.name).join(', ')) : null);
  }

  reasoning(x) {
    return h('div.tl-reason',
      ...[['rival strength', x.oppStrength], ['lambda', x.lambda], ['my gain', x.myGain], ['their gain', x.theirGain],
        ['net', x.net], ['needed', x.required]].map(([k, v]) => h('span', `${k} `, h('b.num', fmt(v)))),
      x.vetoed ? h('span.tl-veto', 'VETO') : null);
  }

  currentCard(r) {
    const c = r.current;
    const names = r.players.map((p) => p.name);
    const verdict = c.vetoed ? ['veto', 'bad'] : c.ok ? ['accept', 'good'] : ['decline', 'warn'];
    return h('div.lens-card.tl-current',
      h('div.upper.muted', 'Offer on the table'),
      h('div.big-line', `${names[c.offerer]} offers ${cards(c.get)} for ${cards(c.give)}`),
      h('div.tl-judge', `${names[c.responder]}'s rule says `, h(`span.badge.tone-${verdict[1]}`, verdict[0])),
      this.reasoning(c));
  }

  decisionsCard(r) {
    const list = h('div.tl-decisions');
    for (const d of [...r.decisions].reverse()) {
      const agree = d.kind === 'answer' ? (d.actual === 'ACCEPT') === (d.verdict === 'accept') : true;
      const text = {
        offer: `offers ${cards(d.give)} for ${cards(d.get)}`,
        answer: `answers ${d.withName}'s offer (${cards(d.give)} for ${cards(d.get)})`,
        deal: `closes the deal with ${d.withName}`, cancel: 'calls the offer off',
      }[d.kind];
      list.append(h('div.tl-decision', { class: agree ? '' : 'differs' },
        h('div.tl-d-head', h('span.tl-d-step.num', `#${d.step}`),
          h('i', { style: { background: `var(--p${d.actor % 6})` } }), h('b', d.actorName), ` ${text}`),
        h('div.tl-d-verdict',
          h('span.badge', d.actual.split(':')[0].toLowerCase()), ' rule now: ',
          h(`span.badge.tone-${{ accept: 'good', ok: 'good', veto: 'bad' }[d.verdict] || 'warn'}`, d.verdict),
          agree ? null : h('span.tiny.muted', ' (differs from what was played)')),
        d.reasoning ? this.reasoning(d.reasoning) : null));
    }
    return h('div.lens-card',
      h('div.upper.muted', 'Recent trade decisions'),
      r.decisions.length ? list : h('div.empty', 'No trades yet. Open the trading bots (Tina, Blake) to see some.'),
      h('p.tiny.muted', 'Each decision is judged again with the knobs above, so you can ask: what if lambda were higher?'));
  }
}
