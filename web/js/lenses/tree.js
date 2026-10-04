/* Tree lens view: the value of the position and of every move, symmetry
 * classes, the principal variation and a two-level tree preview.
 * Result schema: strategy_lab/lenses/tree.py. */

import { h, svg, fmt } from '../dom.js';
import { barList } from '../charts.js';
import { LensView } from './lens.js';

const MODES = {
  exact: ['Exact', 'good', 'The whole tree below this position was searched, so every value is a fact: '
    + 'with best play from both sides, this is the result.'],
  heuristic: ['Depth-limited', 'warn', 'The tree is too big to solve. These values come from looking a few '
    + 'moves ahead and guessing the rest with a heuristic: numbers near +1 look good, near -1 look bad.'],
  estimate: ['Too big', 'bad', 'The tree is too big to solve and this game has no heuristic to guess with.'],
};
const ARROW = '\u{2192}';

export default class TreeLens extends LensView {
  render(r) {
    const b = this.body;
    if (r.mode === 'terminal') {
      b.append(h('div.empty', 'The game is over, so there is no tree left to search.'));
      return;
    }
    const [mode, tone, why] = MODES[r.mode];
    b.append(h('div.lens-card',
      h('div.row.wrap',
        h('span.upper.muted', `${r.moverName} to move`),
        h(`span.badge.tone-${tone}`, mode)),
      h('div.big-line', { style: { color: r.tooBig ? '' : colorOf(r.value, r.mode === 'exact') } },
        r.tooBig ? 'Too big to solve' : r.text),
      h('p.small.muted', why)));
    if (r.tooBig) b.append(estimateCard(r.estimate));
    if (r.symmetry.moves) b.append(symmetryCard(r));
    if (r.actions.length) b.append(valuesCard(r));
    if (r.pv.length) b.append(variationCard(r));
    if (r.tree?.children?.length) b.append(treeCard(r));
    b.append(h('p.tiny.muted', statsLine(r.stats)));
  }
}

function colorOf(v, exact) {
  if (v == null) return 'var(--muted)';
  if (exact) return v > 1e-9 ? 'var(--good)' : v < -1e-9 ? 'var(--bad)' : 'var(--warn)';
  const p = Math.round(((Math.tanh(3 * v) + 1) / 2) * 100);   // small guesses still show a tint
  return `color-mix(in srgb, var(--good) ${p}%, var(--bad))`;
}

function estimateCard(e) {
  return h('div.lens-card',
    h('div.upper.muted', 'How big is it?'),
    h('div.big-line', `about 10^${Math.round(e.log10Size)} lines of play`),
    h('div.stat-row',
      stat('Moves per turn', fmt(e.branching, 1), 'branching factor b'),
      stat('Game length', fmt(e.length, 0), 'plies d')),
    h('p.small', `Random games from here last about ${fmt(e.length, 0)} plies with about ${fmt(e.branching, 1)} `
      + `legal moves each time, so the tree has roughly b^d = ${fmt(e.branching, 1)}^${fmt(e.length, 0)} lines. `
      + 'No computer can list them all, which is why strong play needs a heuristic or a learned policy.'));
}

function symmetryCard(r) {
  const { moves, decisions, classes } = r.symmetry;
  const chips = classes.map((c) => h('span.chip.sym-chip', { title: c.labels.join(', ') },
    c.labels[0], c.members.length > 1 ? h('b', `\u{D7}${c.members.length}`) : null,
    c.text ? h('span.sym-value', { style: { color: colorOf(c.value, r.mode === 'exact') } }, c.text) : null));
  return h('div.lens-card',
    h('div.upper.muted', 'Symmetry'),
    h('div.big-line', `${moves} moves ${ARROW} ${decisions} decision${decisions === 1 ? '' : 's'}`),
    decisions < moves
      ? h('p.small.muted', 'Moves that are rotations, mirrors or swaps of each other lead to positions of the same value, so only one of each group needs to be searched.')
      : h('p.small.muted', 'No two moves are equivalent here, so every move is a different decision.'),
    h('div.row.wrap', chips));
}

function valuesCard(r) {
  const exact = r.mode === 'exact';
  const lo = Math.min(...r.actions.map((a) => a.value));
  const hi = Math.max(...r.actions.map((a) => a.value));
  const length = (v) => (exact || hi - lo < 1e-9
    ? Math.max(0.04, (Math.max(-1, Math.min(1, v)) + 1) / 2)
    : 0.12 + 0.88 * ((v - lo) / (hi - lo)));
  const items = r.actions.map((a) => ({
    label: a.label,
    value: length(a.value),
    max: 1,
    text: a.text,
    color: colorOf(a.value, exact || a.exact),
    cls: a.best ? 'best' : '',
  }));
  return h('div.lens-card',
    h('div.upper.muted', 'Value of each move for the player to move'),
    barList(items),
    h('p.tiny.muted', exact ? 'Bars run from Loss (short) to Win (long). The best moves are bold.'
      : 'Guesses are close together, so the bars compare these moves with each other: longest is best. The best moves are bold.'));
}

function variationCard(r) {
  const first = r.mover;
  const chips = r.pv.map((label, i) => [
    i ? h('span.pv-sep', ARROW) : null,
    h('span.chip.pv-chip', { style: { '--seat': `var(--p${(first + i) % 2})` } }, label)]);
  return h('div.lens-card',
    h('div.upper.muted', 'Best play from here'),
    h('div.row.wrap.pv', chips),
    h('p.tiny.muted', 'The principal variation: each side plays its best move in turn. Colors show who moves.'));
}

/* Root on top, one node per move class below it, replies as small dots. */
function treeCard(r) {
  const exact = r.mode === 'exact';
  const kids = r.tree.children;
  const W = 320;
  const H = 130;
  const [rootY, midY, leafY] = [14, 52, 100];
  const slot = W / kids.length;
  const root = svg('svg.tree-svg', { viewBox: `0 0 ${W} ${H}` });
  const edges = svg('g');
  const nodes = svg('g');
  root.append(edges, nodes);
  kids.forEach((k, i) => {
    const cx = slot * (i + 0.5);
    edges.append(svg('line.tree-edge', { x1: W / 2, y1: rootY, x2: cx, y2: midY, class: k.best ? 'best' : '' }));
    const n = k.children.length;
    const gap = Math.min(9, (slot - 3) / Math.max(1, n));
    k.children.forEach((c, j) => {
      const x = cx + (j - (n - 1) / 2) * gap;
      edges.append(svg('line.tree-edge.thin', { x1: cx, y1: midY, x2: x, y2: leafY, class: c.best ? 'best' : '' }));
      nodes.append(svg('circle.tree-node', {
        cx: x, cy: leafY, r: Math.max(1.6, Math.min(3.6, gap / 2.3)),
        class: c.best ? 'ring' : '', style: { fill: colorOf(c.value, exact) } },
      svg('title', `${k.label}, then ${c.label}: ${c.text}`)));
    });
    nodes.append(svg('circle.tree-node', { cx, cy: midY, r: 7, class: k.best ? 'ring' : '',
      style: { fill: colorOf(k.value, exact) } }, svg('title', `${k.label}: ${k.text}`)));
    if (slot >= 22) {
      nodes.append(svg('text.axis', { x: cx, y: midY + 20, 'text-anchor': 'middle' },
        k.label.split(' ').pop().slice(0, 5) + (k.size > 1 ? `\u{D7}${k.size}` : '')));
    }
  });
  nodes.append(svg('circle.tree-node', { cx: W / 2, cy: rootY, r: 9, style: { fill: colorOf(r.tree.value, exact) } },
    svg('title', 'the position now')));
  return h('div.lens-card',
    h('div.upper.muted', 'The tree, two levels deep'),
    root,
    h('p.tiny.muted', 'Top: the position now. Middle: your moves, one per symmetry class. Bottom: the '
      + "opponent's replies (up to 6 each). Green is good for you, red is bad. Thick lines and rings mark the best choice "
      + 'of whoever is moving.'));
}

function statsLine(s) {
  const parts = [`${s.searched.toLocaleString()} positions created`];
  if (s.distinct != null) parts.push(`${s.distinct.toLocaleString()} distinct after symmetry`);
  if (s.branching) parts.push(`${fmt(s.branching, 1)} moves per position`);
  if (s.depth) parts.push(`${s.depth} plies deep`);
  parts.push(`${Math.round(s.seconds * 1000)} ms`);
  return parts.join(' \u{B7} ');
}

function stat(label, value, sub) {
  return h('div.stat', h('span.stat-label', label), h('span.stat-value.num', value), sub ? h('span.stat-sub', sub) : null);
}
