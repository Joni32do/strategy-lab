/* Learn lens view: train an algorithm and read the curves, the value map
 * with policy arrows (grid worlds) or the arm estimates and regret
 * (bandits). Training runs on "Train", not on every move.
 * Result schema: strategy_lab/lenses/rl.py. */

import { h, fmt, pct } from '../dom.js';
import { barList, lineChart } from '../charts.js';
import { LensView } from './lens.js';

const ARROWS = { up: '\u{2191}', right: '\u{2192}', down: '\u{2193}', left: '\u{2190}' };
const SEATS = [0, 1, 2, 3, 4, 5].map((i) => `var(--p${i})`);
const NOTES = {
  'value-iteration': 'Planning: the model is known, so repeat the Bellman backup (value = reward + discounted value of the best next state) until nothing changes.',
  'q-learning': 'Learning from experience: after every step, nudge Q(state, move) toward reward + gamma times the best Q of the next state. Ties are broken at random.',
  'epsilon-greedy': 'Pull the best average so far, but with probability epsilon pull a random arm.',
  ucb: 'UCB1: pull the arm with the best average plus a bonus for arms you know little about.',
  softmax: 'Pull arm i with probability proportional to exp(average / temperature).',
};

export default class RLLens extends LensView {
  static auto = false;

  runLabel() { return 'Train'; }

  render(r) {
    const b = this.body;
    b.append(h('div.lens-card',
      h('div.upper.muted', 'Algorithm'),
      h('div.big-line', r.algorithm),
      h('p.small.muted', NOTES[r.algorithm] || '')));
    if (r.kind === 'gridworld') this.grid(r);
    else this.bandit(r);
  }

  grid(r) {
    const b = this.body;
    const ev = r.evaluation;
    b.append(h('div.lens-card',
      h('div.upper.muted', `The greedy policy, played ${ev.episodes} times`),
      h('div.stat-row',
        stat('Reaches the goal', pct(ev.successRate), 'success rate'),
        stat('Mean return', fmt(ev.meanReturn), 'per game'),
        stat('Mean length', fmt(ev.meanLength, 1), 'steps'))));
    b.append(h('div.lens-card', h('div.upper.muted', 'Value of each tile and the best move'),
      heatmap(r),
      h('p.tiny.muted', 'Color: how good it is to stand here (green high, red low). Arrow: the move with the highest Q-value. '
        + 'No arrow means the algorithm has not learned a preference yet.')));
    this.curves(r);
  }

  bandit(r) {
    const b = this.body;
    if (r.practice) {
      b.append(h('p.small.muted', 'Training on a practice bandit with the same number of arms, not the one you are playing, so its odds stay hidden. '
        + 'After the last pull this view uses the real arms.'));
    }
    const series = r.arms.map((name, i) => ({ values: r.estimates.arms[i], color: SEATS[i % 6], label: `Arm ${name}` }));
    b.append(h('div.lens-card', h('div.upper.muted', 'Estimated payout of each arm'),
      lineChart({ series, height: 140, yMin: 0, yMax: 1, xLabel: 'pull' }),
      h('p.tiny.muted', 'Estimates wobble at first and settle as an arm is pulled more. The algorithm decides how many pulls each arm gets.')));
    const g = r.regret;
    const regretSeries = [{ values: g.values, color: 'var(--accent)', label: r.algorithm },
      { values: g.values.map((_, i) => (g.baseline * (i + 1)) / g.values.length), color: 'var(--muted)',
        label: 'random player', dashed: true }];
    const card = h('div.lens-card', h('div.upper.muted', 'Cumulative regret'),
      lineChart({ series: regretSeries, height: 140, yMin: 0, xLabel: 'pull', yLabel: 'payout lost against always pulling the best arm' }));
    card.append(h('p.small', `After ${r.options.episodes} pulls: regret ${fmt(g.values[g.values.length - 1], 1)} against ${fmt(g.baseline, 1)} for pulling at random.`));
    if (r.you) card.append(h('p.small', `Your game: regret ${fmt(r.you.regret, 1)}, ${fmt(r.you.reward, 0)} payouts.`));
    b.append(card);
    if (g.probs) {
      b.append(h('div.lens-card', h('div.upper.muted', 'True odds'),
        barList(g.probs.map((p, i) => ({ label: `Arm ${r.arms[i]}`, value: p, max: 1, text: fmt(p),
          color: i === g.best ? 'var(--good)' : SEATS[i % 6] })))));
    }
    this.curves(r);
  }

  curves(r) {
    const b = this.body;
    const c = r.curve;
    const bellman = c.kind === 'bellman-error';
    const series = [{ values: c.values, color: 'var(--c-sky)', label: bellman ? 'largest change' : 'each' }];
    if (c.average) series.push({ values: c.average, color: 'var(--accent)', label: `average of ${c.window}` });
    const what = { return: 'Return per episode', reward: 'Reward per pull', 'bellman-error': 'Bellman error per sweep' }[c.kind];
    b.append(h('div.lens-card', h('div.upper.muted', what),
      lineChart({ series, height: 140, xLabel: bellman ? 'sweep' : (r.kind === 'bandit' ? 'pull' : 'episode'),
        yMin: bellman ? 0 : undefined }),
      h('p.tiny.muted', bellman ? 'Values change less and less each sweep: the plan has converged.'
        : 'The light line is noisy luck. The average line shows the trend: is the agent getting better?')));
    if (r.entropy) {
      b.append(h('div.lens-card', h('div.upper.muted', 'Policy entropy'),
        lineChart({ series: [{ values: r.entropy.values, color: 'var(--c-teal)' }], height: 110, yMin: 0,
          yMax: r.entropy.max, xLabel: r.kind === 'bandit' ? 'pull' : 'episode', yLabel: 'bits' }),
        h('p.tiny.muted', `High entropy (up to ${fmt(r.entropy.max)} bits) means exploring: nearly random choices. `
          + 'It falls as the agent becomes sure which move is best. It never reaches 0 while epsilon is above 0.')));
    }
  }
}

function heatmap(r) {
  const live = (i) => !'GHC'.includes(r.tiles[Math.floor(i / r.cols)][i % r.cols]);
  const vals = Object.entries(r.values).filter(([i]) => live(+i)).map(([, v]) => v);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const big = r.cols > 8;
  const cells = [];
  for (let i = 0; i < r.rows * r.cols; i++) {
    const tile = r.tiles[Math.floor(i / r.cols)][i % r.cols];
    const v = r.values[i];
    const el = h('div.hm-cell', { class: `tile-${tile === '#' ? 'wall' : tile}` });
    if (v != null && live(i)) {
      const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
      el.style.background = `color-mix(in srgb, color-mix(in srgb, var(--good) ${Math.round(t * 100)}%, var(--bad)) 55%, var(--surface))`;
    }
    el.title = v != null ? `value ${fmt(v, 3)}` : '';
    const mark = { G: 'goal', H: 'hole', C: 'cliff', S: 'start' }[tile];
    if (mark) el.append(h('span.hm-mark', big ? tile : mark));
    const arrow = r.policy[i];
    if (arrow) el.append(h('span.hm-arrow', ARROWS[arrow]));
    if (v != null && !big && live(i)) el.append(h('span.hm-value.num', fmt(v, Math.abs(v) >= 10 ? 0 : 2)));
    cells.push(el);
  }
  return h('div.heatmap', { style: { gridTemplateColumns: `repeat(${r.cols}, 1fr)` } }, cells);
}

function stat(label, value, sub) {
  return h('div.stat', h('span.stat-label', label), h('span.stat-value.num', value), sub ? h('span.stat-sub', sub) : null);
}
