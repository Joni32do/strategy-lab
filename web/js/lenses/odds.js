/* Odds lens view: the last chance event, surprise vs entropy, and Monte
 * Carlo win rates per move. Result schema: strategy_lab/lenses/odds.py. */

import { h, pct, prob, fmt } from '../dom.js';
import { barList } from '../charts.js';
import { LensView } from './lens.js';

export default class OddsLens extends LensView {
  render(r) {
    const b = this.body;
    if (r.last) {
      const L = r.last;
      const card = h('div.lens-card',
        h('div.upper.muted', 'Last chance event'),
        h('div.big-line', L.text),
        h('div.stat-row',
          stat('Probability', prob(L.prob), L.prob != null ? pct(L.prob, 1) : ''),
          stat('Surprise', L.surprise != null ? `${fmt(L.surprise)} bits` : '-', '-log2 p'),
          stat('Entropy', L.entropy != null ? `${fmt(L.entropy)} bits` : '-', 'average surprise')));
      if (L.distribution?.length) {
        const max = Math.max(...L.distribution.map((d) => d.p));
        card.append(h('div.dist', L.distribution.map((d) =>
          h('div.dist-col', { class: d.hit ? 'hit' : '', title: `${d.label}: ${pct(d.p, 1)}` },
            h('span.dist-bar', { style: { height: `${(d.p / max) * 100}%` } }),
            h('span.dist-label', d.label.length > 4 ? d.label.slice(0, 4) : d.label)))));
      }
      b.append(card);
    }
    if (r.luck && r.luck.events) {
      const ratio = r.luck.expected ? r.luck.surprise / r.luck.expected : 1;
      b.append(h('div.lens-card',
        h('div.upper.muted', 'Surprise this game'),
        h('p.small', `${r.luck.events} chance events produced ${fmt(r.luck.surprise, 1)} bits of surprise; `
          + `an average game of the same length produces ${fmt(r.luck.expected, 1)}. `
          + (ratio > 1.15 ? 'Rarer outcomes than usual so far.' : ratio < 0.85 ? 'More common outcomes than usual so far.' : 'About as surprising as an average game.')),
        h('div.meter', h('span', { style: { width: `${Math.min(100, ratio * 50)}%` } }), h('i'))));
    }
    if (r.moves?.length) {
      b.append(h('div.lens-card',
        h('div.upper.muted', `Win rate per move (${r.moves[0].n} games each, ${r.policy})`),
        barList(r.moves.map((m, i) => ({
          label: m.label,
          value: m.rate,
          max: 1,
          text: `${pct(m.rate)}${m.stderr != null ? ` \u{B1}${Math.round(m.stderr * 100)}` : ''}`,
          color: i === 0 ? 'var(--good)' : 'var(--accent)',
        }))),
        h('p.tiny.muted', 'Each move is played, then the game is finished many times at random. '
          + 'More games per move shrink the \u{B1} error: the law of large numbers.')));
    } else if (!r.last) {
      b.append(h('div.empty', 'Odds appear when it is your move or after a roll.'));
    }
  }
}

function stat(label, value, sub) {
  return h('div.stat', h('span.stat-label', label), h('span.stat-value.num', value), sub ? h('span.stat-sub', sub) : null);
}
