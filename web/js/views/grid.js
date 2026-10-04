/* GridView: boards of cells (Tic-Tac-Toe, Connect Four, chess, grid worlds,
 * Snakes & Ladders, the Maedn cross).
 *
 * Part: {view: "grid", rows, cols, cells: [cell | null], style, links,
 *        lines, coords}. See strategy_lab/core/scene.py for the fields.
 *
 * Skins subclass this and override drawCell / drawLinks / drawLines. */

import { h, svg } from '../dom.js';
import { icon } from '../icons.js';
import { View } from './view.js';
import { arrowSvg, pieceSvg } from './pieces.js';

export class GridView extends View {
  static type = 'grid';

  render(part, prev) {
    if (prev && prev !== part) this.selected = null;
    const { rows, cols } = part;
    // Two-click moves (chess): cells may list {to, action, label} moves.
    this.dests = new Map();
    const from = this.selected != null ? part.cells[this.selected] : null;
    for (const m of from?.moves || []) {
      if (!this.dests.has(m.to) || /=Q/.test(m.label)) this.dests.set(m.to, m);
    }
    const board = h(`div.grid-board.style-${part.style || 'board'}`, {
      style: { '--rows': rows, '--cols': cols, aspectRatio: `${cols} / ${rows}` },
    });
    part.cells.forEach((c, i) => board.append(this.drawCell(c, i, part)));
    const layer = svg('svg.grid-layer', { viewBox: `0 0 ${cols * 10} ${rows * 10}`, preserveAspectRatio: 'none' });
    this.drawLinks(layer, part);
    this.drawLines(layer, part);
    board.append(layer);
    const wrap = h('div.grid-wrap', { class: part.coords ? 'with-coords' : '' }, board);
    if (part.coords) this.drawCoords(wrap, part);
    this.el.append(wrap);
  }

  cellCenter(i, part) {
    const r = Math.floor(i / part.cols);
    const c = i % part.cols;
    return [c * 10 + 5, r * 10 + 5];
  }

  drawCell(c, i, part) {
    if (!c) return h('div.cell.void');
    const r = Math.floor(i / part.cols);
    const col = i % part.cols;
    const tone = c.tone || (part.style === 'checker' ? ((r + col) % 2 ? 'dark' : 'light') : '');
    const el = h('div.cell', { class: tone ? `tone-${tone}` : '' });
    if (c.label) el.append(h('span.cell-label', c.label));
    if (c.icon) el.append(h('span.cell-icon', icon(c.icon)));
    if (c.text) el.append(h('span.cell-text', c.text));
    if (c.pieces?.length) {
      const stack = h('div.cell-pieces', { class: c.pieces.length > 1 ? 'many' : '' });
      for (const p of c.pieces) stack.append(pieceSvg(p));
      el.append(stack);
    }
    if (c.arrow) el.append(h('span.cell-arrow', arrowSvg(c.arrow)));
    if (c.badge) el.append(h('span.cell-badge', c.badge));
    if (c.moves?.length) {
      el.classList.add('movable');
      if (i === this.selected) el.classList.add('selected');
      el.addEventListener('click', () => {
        if (!this.ctx.interactive()) return;
        this.selected = this.selected === i ? null : i;
        this.update(this.part);
      });
    }
    const dest = this.dests?.get(i);
    if (dest && c.action == null) {
      el.classList.add('dest');
      el.title = dest.label;
      return this.actionable(el, dest.action);
    }
    return this.actionable(el, c.action);
  }

  drawLinks(layer, part) {
    for (const ln of part.links || []) {
      const [x1, y1] = this.cellCenter(ln.from, part);
      const [x2, y2] = this.cellCenter(ln.to, part);
      if (ln.kind === 'up') layer.append(ladder(x1, y1, x2, y2));
      else if (ln.kind === 'down') layer.append(snake(x1, y1, x2, y2));
      else layer.append(svg('line.link-arrow', { x1, y1, x2, y2 }));
    }
  }

  drawLines(layer, part) {
    for (const line of part.lines || []) {
      if (line.length < 2) continue;
      const [x1, y1] = this.cellCenter(line[0], part);
      const [x2, y2] = this.cellCenter(line[line.length - 1], part);
      layer.append(svg('line.win-line', { x1, y1, x2, y2 }));
    }
  }

  drawCoords(wrap, part) {
    const files = h('div.coords-files', { style: { '--cols': part.cols } });
    for (let c = 0; c < part.cols; c++) files.append(h('span', 'abcdefghijklmnop'[c]));
    const ranks = h('div.coords-ranks', { style: { '--rows': part.rows } });
    for (let r = 0; r < part.rows; r++) ranks.append(h('span', String(part.rows - r)));
    wrap.append(ranks, files);
  }
}

function ladder(x1, y1, x2, y2) {
  const g = svg('g.link-ladder');
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const nx = (-dy / len) * 1.6;
  const ny = (dx / len) * 1.6;
  g.append(svg('line', { x1: x1 + nx, y1: y1 + ny, x2: x2 + nx, y2: y2 + ny }));
  g.append(svg('line', { x1: x1 - nx, y1: y1 - ny, x2: x2 - nx, y2: y2 - ny }));
  const rungs = Math.max(2, Math.floor(len / 4));
  for (let k = 1; k < rungs; k++) {
    const t = k / rungs;
    const cx = x1 + dx * t;
    const cy = y1 + dy * t;
    g.append(svg('line.rung', { x1: cx + nx, y1: cy + ny, x2: cx - nx, y2: cy - ny }));
  }
  return g;
}

function snake(x1, y1, x2, y2) {
  const g = svg('g.link-snake');
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const nx = (-dy / len) * 4;
  const ny = (dx / len) * 4;
  const d = `M${x1},${y1} C${x1 + dx * 0.3 + nx},${y1 + dy * 0.3 + ny} ${x1 + dx * 0.7 - nx},${y1 + dy * 0.7 - ny} ${x2},${y2}`;
  g.append(svg('path.body', { d }));
  g.append(svg('circle.head', { cx: x1, cy: y1, r: 1.6 }));
  return g;
}
