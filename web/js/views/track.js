/* TrackView: spaces along a path with tokens (Monopoly ring, Life road).
 *
 * Part: {view: "track", spaces: [{label, sub, tone, icon, owner, level,
 *        action}], tokens: [{owner, at, label}], shape: ring|line|serpentine}
 *
 * The ring puts space 0 in the bottom-right corner and runs clockwise
 * along the bottom, up the left, along the top and down the right side,
 * like a Monopoly board. */

import { h } from '../dom.js';
import { icon } from '../icons.js';
import { View } from './view.js';

export class TrackView extends View {
  static type = 'track';

  render(part) {
    const n = part.spaces.length;
    const shape = part.shape === 'ring' && n % 4 === 0 && n >= 8 ? 'ring' : (part.shape || 'line');
    const byPos = new Map();
    for (const t of part.tokens || []) {
      if (!byPos.has(t.at)) byPos.set(t.at, []);
      byPos.get(t.at).push(t);
    }
    const cells = part.spaces.map((sp, i) => this.drawSpace(sp, i, byPos.get(i) || []));
    let board;
    if (shape === 'ring') {
      const k = n / 4;
      board = h('div.track-ring', { style: { '--k': k + 1 } });
      cells.forEach((el, i) => {
        const [row, col] = ringPos(i, k);
        el.style.gridRow = String(row + 1);
        el.style.gridColumn = String(col + 1);
        if (i % k === 0) el.classList.add('corner');
        board.append(el);
      });
      board.append(h('div.track-center', { style: { gridRow: `2 / ${k + 1}`, gridColumn: `2 / ${k + 1}` } },
        part.caption ? h('div.track-title', part.caption) : null));
    } else if (shape === 'serpentine') {
      const w = Math.min(10, Math.ceil(Math.sqrt(n * 1.6)));
      board = h('div.track-serp', { style: { '--w': w } });
      cells.forEach((el, i) => {
        const row = Math.floor(i / w);
        const col = row % 2 === 0 ? i % w : w - 1 - (i % w);
        el.style.gridRow = String(row + 1);
        el.style.gridColumn = String(col + 1);
        board.append(el);
      });
    } else {
      board = h('div.track-line', cells);
    }
    this.el.append(board);
  }

  drawSpace(sp, i, tokens) {
    const el = h('div.space', { class: sp.tone ? `tone-${sp.tone}` : '' });
    if (sp.owner != null) {
      el.classList.add('owned');
      el.style.setProperty('--owner', this.color(sp.owner));
    }
    el.append(h('div.space-band'));
    if (sp.icon) el.append(h('span.space-icon', icon(sp.icon)));
    el.append(h('div.space-label', sp.label));
    if (sp.sub) el.append(h('div.space-sub', sp.sub));
    if (sp.level) {
      const pips = h('div.space-level');
      for (let k = 0; k < sp.level; k++) pips.append(h('i'));
      el.append(pips);
    }
    if (tokens.length) {
      el.append(h('div.space-tokens', tokens.map((t) =>
        h('span.tok', { style: { background: this.color(t.owner) }, title: this.name(t.owner) }, t.label || ''))));
    }
    return this.actionable(el, sp.action);
  }
}

function ringPos(i, k) {
  if (i <= k) return [k, k - i];                 // bottom row, right to left
  if (i <= 2 * k) return [k - (i - k), 0];        // left column, bottom to top
  if (i <= 3 * k) return [0, i - 2 * k];          // top row, left to right
  return [i - 3 * k, k];                          // right column, top to bottom
}
