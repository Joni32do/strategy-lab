/* Nash lens view: equilibria, dominance, how predictable you are, and
 * regret-matching self-play converging to the equilibrium.
 * Result schema: strategy_lab/lenses/nash.py. */

import { h, fmt, pct, prob } from '../dom.js';
import { barList, lineChart, simplex } from '../charts.js';
import { LensView } from './lens.js';

const p3 = (p) => (p > 0.999 ? '1' : p < 0.001 ? '0' : prob(p));
const argmax = (xs) => xs.reduce((best, v, i) => (v > xs[best] + 1e-9 ? i : best), 0);

export default class NashLens extends LensView {
  static auto = true;

  render(r) {
    const b = this.body;
    b.append(equilibriaCard(r), dominanceCard(r), youCard(r), regretCard(r));
  }
}

function equilibriaCard(r) {
  const card = h('div.lens-card', h('div.upper.muted', 'Nash equilibria'));
  if (r.zeroSum) card.append(h('p.small.muted', 'Zero-sum: what one seat wins the other loses.'));
  if (!r.equilibria.length) card.append(h('p.small.muted', 'This table is too big to enumerate.'));
  for (const eq of r.equilibria) {
    const mixes = [eq.row, eq.col];
    const head = h('div.row.wrap',
      h('strong', eq.pure ? 'Pure equilibrium' : 'Mixed equilibrium'),
      h('span.badge.tone-warn', eq.method),
      h('span.small.muted.num', `payoffs ${fmt(eq.payoffs[0])} / ${fmt(eq.payoffs[1])}`));
    let body;
    if (eq.pure) {
      body = h('div.row.wrap', mixes.map((m, seat) => h('span.chip.eq-chip', { style: { '--seat': `var(--p${seat})` } },
        `${r.seats[seat]}: ${r.labels[seat][argmax(m)]}`)));
    } else {
      body = h('div.eq-grid', mixes.map((m, seat) => h('div.eq-col',
        h('div.tiny.muted', r.seats[seat]),
        barList(r.labels[seat].map((l, i) => ({ label: l, value: m[i], max: 1, text: p3(m[i]),
          color: `var(--p${seat})` }))))));
    }
    card.append(h('div.eq', head, body));
  }
  card.append(h('p.tiny.muted', 'At an equilibrium nobody gains by changing only their own strategy.'));
  return card;
}

function dominanceCard(r) {
  const d = r.dominance;
  const lines = [];
  [0, 1].forEach((seat) => {
    const names = r.labels[seat];
    if (d.dominant[seat] != null) lines.push(`${r.seats[seat]}: ${names[d.dominant[seat]]} is dominant, best whatever the other does.`);
    // a dominant move already implies that every other move is dominated
    for (const x of d.dominant[seat] != null ? [] : d.dominated[seat]) lines.push(`${r.seats[seat]}: ${names[x.action]} is dominated by ${names[x.by]}.`);
  });
  const left = d.survivors.map((s, seat) => s.map((i) => r.labels[seat][i]));
  const reduced = d.survivors[0].length < r.labels[0].length || d.survivors[1].length < r.labels[1].length;
  return h('div.lens-card',
    h('div.upper.muted', 'Dominance'),
    lines.length ? h('ul.notes', lines.map((l) => h('li.small', l)))
      : h('p.small', 'No move is dominant or dominated: the best move depends on what the other player does.'),
    reduced ? h('p.small', `After removing dominated moves, only ${left[0].join('/')} against ${left[1].join('/')} remains.`) : null);
}

/* Payoff of the opponent's actions against your empirical mix. */
function opponentReply(r) {
  const me = r.me;
  const f = r.you.freq;
  const opp = 1 - me;
  const values = r.labels[opp].map((_, k) => f.reduce((acc, fi, i) => acc
    + fi * (me === 0 ? r.payoffs[i][k][1] : r.payoffs[k][i][0]), 0));
  const top = Math.max(...values);
  return r.labels[opp].filter((_, k) => values[k] >= top - 1e-9);
}

function youCard(r) {
  const card = h('div.lens-card', h('div.upper.muted', `You (${r.seats[r.me]})`));
  const y = r.you;
  if (!y) {
    card.append(h('p.small.muted', 'Play a round to see your habits: how often you pick each move, and how much that gives away.'));
    return card;
  }
  const eq = r.regret.equilibrium ? (r.me === 0 ? r.regret.equilibrium.row : r.regret.equilibrium.col) : null;
  card.append(h('p.small.muted', `After ${r.rounds} round${r.rounds === 1 ? '' : 's'}. Bright bar: how often you played the move. Grey bar: the equilibrium mix.`));
  card.append(h('div.freqs', r.labels[r.me].map((label, i) => h('div.freq-row',
    h('span.barlist-label', label),
    h('div.dual',
      h('span.track', h('span.fill', { style: { width: pct(y.freq[i]), background: `var(--p${r.me})` } })),
      eq ? h('span.track', h('span.fill.ref', { style: { width: pct(eq[i]) } })) : null),
    h('span.num.small', pct(y.freq[i]))))));
  card.append(h('div.meter-line',
    h('span.small', `Entropy ${fmt(y.entropy)} of ${fmt(y.maxEntropy)} bits`),
    h('div.meter.plain', h('span', { style: { width: pct(y.maxEntropy ? y.entropy / y.maxEntropy : 0) } }))));
  const exploit = y.exploitability;
  card.append(h('div.stat-row',
    stat('Predictability', pct(y.predictability), 'of the way to a fixed move'),
    stat('Exploitable', exploit == null ? '-' : fmt(exploit), 'points per round'),
    stat('Safe level',y.guarantee == null ? '-' : fmt(y.guarantee), 'per round')));
  card.append(h('p.small', exploit > 0.05
    ? `A player who knows your mix could play ${opponentReply(r).join(' or ')} and hold you ${fmt(exploit)} below what you can guarantee. More surprise (entropy) means less to exploit.`
    : 'Nothing to exploit: a player who knows your mix cannot push you below what you can guarantee.'));
  card.append(h('p.small', `Against how they played so far, your best reply is ${y.bestResponseLabels.join(' or ')} (shown on the board).`));
  return card;
}

function regretCard(r) {
  const pts = r.regret.points;
  const n = r.labels[0].length;
  const eq = r.regret.equilibrium;
  const card = h('div.lens-card', h('div.upper.muted', `Regret matching, ${r.regret.iterations} rounds of self-play`));
  if (n === 3) {
    card.append(simplex({ points: pts.map((p) => p.row), labels: r.labels[0], target: eq ? eq.row : null, color: 'var(--p0)' }));
    card.append(h('p.small', `The line is the average strategy of ${r.seats[0]} as both seats learn from regret. The ring is the equilibrium.`));
  } else if (n === 2) {
    const series = [
      { values: pts.map((p) => p.row[0]), color: 'var(--p0)', label: `${r.seats[0]}: ${r.labels[0][0]}` },
      { values: pts.map((p) => p.col[0]), color: 'var(--p1)', label: `${r.seats[1]}: ${r.labels[1][0]}` },
    ];
    card.append(lineChart({ series, height: 130, yMin: 0, yMax: 1, xLabel: 'iterations (log scale)',
      yLabel: `probability of ${r.labels[0][0]}`,
      refLines: eq ? [{ y: eq.row[0], label: 'Nash' }] : [] }));
  }
  card.append(lineChart({ series: [{ values: pts.map((p) => p.gap), color: 'var(--c-amber)', label: 'distance from equilibrium' }],
    height: 100, yMin: 0, xLabel: 'iterations (log scale)' }));
  card.append(h('p.tiny.muted', 'Each round both seats favor the moves they regret not having played. Their average strategies '
    + (r.zeroSum ? 'converge to the equilibrium in a zero-sum game.' : 'settle on an equilibrium; in other games which one can depend on the start.')));
  return card;
}

function stat(label, value, sub) {
  return h('div.stat', h('span.stat-label', label), h('span.stat-value.num', value), sub ? h('span.stat-sub', sub) : null);
}
