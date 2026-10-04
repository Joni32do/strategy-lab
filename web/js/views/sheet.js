/* SheetView: a roll-and-write score sheet (Qwixx).
 *
 * Part: {view: "sheet", title, owner, rows: [{color, cells: [{label, crossed,
 *        action, lock}], locked, score}], penalties, maxPenalties,
 *        penaltyAction, score, active, compact} */

import { h } from '../dom.js';
import { icon } from '../icons.js';
import { View } from './view.js';

export class SheetView extends View {
  static type = 'sheet';

  render(part) {
    const sheet = h('div.sheet', { class: `${part.compact ? 'compact' : ''}${part.active ? ' active' : ''}` });
    if (part.owner != null) sheet.style.setProperty('--owner', this.color(part.owner));
    sheet.append(h('div.sheet-head', h('span.sheet-title', part.title || ''),
      part.score != null ? h('span.sheet-score.num', String(part.score)) : null));
    for (const row of part.rows) {
      const r = h('div.sheet-row', { class: `c-${row.color}${row.locked ? ' locked' : ''}` });
      for (const c of row.cells) {
        const cell = h('span.sheet-cell', { class: `${c.crossed ? 'crossed' : ''}${c.lock ? ' lock' : ''}${c.tone ? ` tone-${c.tone}` : ''}` },
          c.lock ? icon('lock') : c.label);
        r.append(this.actionable(cell, c.action));
      }
      if (row.score != null) r.append(h('span.sheet-rowscore.num', String(row.score)));
      sheet.append(r);
    }
    const pens = h('div.sheet-pens', h('span.small.muted', 'Penalties'));
    for (let i = 0; i < (part.maxPenalties ?? 4); i++) {
      const box = h('span.pen', { class: i < (part.penalties || 0) ? 'crossed' : '' });
      if (i === (part.penalties || 0)) this.actionable(box, part.penaltyAction);
      pens.append(box);
    }
    sheet.append(pens);
    this.el.append(sheet);
  }
}
