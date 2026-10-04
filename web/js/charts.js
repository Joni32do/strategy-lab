/* Small SVG charts for lenses and the history page. No dependencies.
 *
 *   lineChart({series: [{values, color, label, dashed}], height, yMin, yMax,
 *              xLabel, yLabel, refLines: [{y, label}]})
 *   barList([{label, value, max, color, text}])
 *   splitBar([{value, color, label}])          one stacked 100% bar
 *   simplex({points: [[a, b, c], ...], labels, target})   3-action mixes
 */

import { h, svg } from './dom.js';

export function lineChart({ series, height = 150, yMin, yMax, xLabel = '', yLabel = '',
  refLines = [] }) {
  const W = 320;
  const H = height;
  const pad = { l: 34, r: 8, t: 8, b: xLabel ? 24 : 12 };
  const all = series.flatMap((s) => s.values).filter((v) => v != null && Number.isFinite(v));
  let lo = yMin ?? Math.min(0, ...all);
  let hi = yMax ?? Math.max(...all, lo + 1e-9);
  if (hi - lo < 1e-9) { hi = lo + 1; }
  const n = Math.max(2, ...series.map((s) => s.values.length));
  const x = (i) => pad.l + (i / (n - 1)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
  const root = svg('svg.chart', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' });
  for (const t of [lo, (lo + hi) / 2, hi]) {
    root.append(svg('line.grid', { x1: pad.l, x2: W - pad.r, y1: y(t), y2: y(t) }));
    root.append(svg('text.axis', { x: pad.l - 5, y: y(t) + 3, 'text-anchor': 'end' }, short(t)));
  }
  for (const r of refLines) {
    root.append(svg('line.ref', { x1: pad.l, x2: W - pad.r, y1: y(r.y), y2: y(r.y) }));
    if (r.label) root.append(svg('text.axis.ref-label', { x: W - pad.r, y: y(r.y) - 4, 'text-anchor': 'end' }, r.label));
  }
  for (const s of series) {
    const pts = s.values.map((v, i) => (v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
    if (!pts.length) continue;
    root.append(svg('polyline.series', {
      points: pts.join(' '),
      style: { stroke: s.color || 'var(--accent)' },
      'stroke-dasharray': s.dashed ? '4 4' : null,
    }));
  }
  if (xLabel) root.append(svg('text.axis', { x: (W + pad.l) / 2, y: H - 4, 'text-anchor': 'middle' }, xLabel));
  const legend = series.filter((s) => s.label).map((s) =>
    h('span.legend-item', h('i', { style: { background: s.color || 'var(--accent)' } }), s.label));
  return h('figure.chart-wrap', root, legend.length ? h('figcaption.legend', legend) : null,
    yLabel ? h('div.chart-ylabel', yLabel) : null);
}

function short(v) {
  const a = Math.abs(v);
  if (a >= 1000) return `${(v / 1000).toFixed(1)}k`;
  if (a >= 10 || Number.isInteger(v)) return String(Math.round(v));
  return v.toFixed(2);
}

export function barList(items) {
  const max = Math.max(1e-9, ...items.map((it) => it.max ?? Math.abs(it.value)));
  return h('div.barlist', items.map((it) => h('div.barlist-row', { class: it.cls || '' },
    h('span.barlist-label', it.label),
    h('span.barlist-track', h('span.barlist-fill', {
      style: { width: `${Math.max(0, Math.min(100, (Math.abs(it.value) / (it.max ?? max)) * 100))}%`,
        background: it.color || 'var(--accent)' },
    })),
    h('span.barlist-value.num', it.text ?? String(it.value)))));
}

export function splitBar(parts) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return h('div.splitbar', parts.map((p) => h('span', {
    style: { width: `${(p.value / total) * 100}%`, background: p.color },
    title: `${p.label}: ${p.value}`,
  }, p.value / total > 0.12 ? `${p.label} ${p.value}` : '')));
}

/* A triangle where each corner is one pure action: every mixed strategy
 * over three actions is a point inside. */
export function simplex({ points = [], labels = ['A', 'B', 'C'], target = null, color = 'var(--accent)' }) {
  const W = 220;
  const H = 200;
  const A = [W / 2, 14];
  const B = [14, H - 22];
  const C = [W - 14, H - 22];
  const at = ([a, b, c]) => {
    const s = a + b + c || 1;
    return [(a * A[0] + b * B[0] + c * C[0]) / s, (a * A[1] + b * B[1] + c * C[1]) / s];
  };
  const root = svg('svg.simplex', { viewBox: `0 0 ${W} ${H}` });
  root.append(svg('polygon.simplex-tri', { points: [A, B, C].map((p) => p.join(',')).join(' ') }));
  root.append(svg('text.axis', { x: A[0], y: A[1] - 3, 'text-anchor': 'middle' }, labels[0]));
  root.append(svg('text.axis', { x: B[0], y: B[1] + 14, 'text-anchor': 'start' }, labels[1]));
  root.append(svg('text.axis', { x: C[0], y: C[1] + 14, 'text-anchor': 'end' }, labels[2]));
  if (points.length) {
    const pts = points.map(at);
    root.append(svg('polyline.series', { points: pts.map((p) => p.map((v) => v.toFixed(1)).join(',')).join(' '), style: { stroke: color } }));
    const end = pts[pts.length - 1];
    root.append(svg('circle.simplex-end', { cx: end[0], cy: end[1], r: 4.5, style: { fill: color } }));
  }
  if (target) {
    const t = at(target);
    root.append(svg('circle.simplex-target', { cx: t[0], cy: t[1], r: 6 }));
  }
  return root;
}
