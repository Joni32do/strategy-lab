/* Minimal: no decoration, just the game. Boards become characters:
 * AsciiGridView extends GridView and draws every cell as one glyph. */

import { h } from '../dom.js';
import { GridView } from '../views/grid.js';
import { DiceView } from '../views/dice.js';
import { Skin } from './skin.js';

const SHAPES = { x: 'X', o: 'O', disc: '\u{25CF}', token: '\u{25CF}', agent: '@' };

export class AsciiGridView extends GridView {
  static type = 'grid';

  drawCell(c, i, part) {
    if (!c) return h('div.cell.void');
    let ch = c.text || '\u{B7}';
    if (c.pieces?.length) {
      const p = c.pieces[c.pieces.length - 1];
      ch = p.shape === 'glyph' ? p.glyph : (SHAPES[p.shape] || '\u{25CF}');
    }
    const el = h('div.cell.ascii', { class: c.tone ? `tone-${c.tone}` : '' },
      h('span', { style: { color: c.pieces?.length ? this.color(c.pieces[c.pieces.length - 1].owner) : null } }, ch));
    if (c.label) el.append(h('span.cell-label', c.label));
    return this.actionable(el, c.action);
  }
}

export class PlainDiceView extends DiceView {
  static type = 'dice';

  render(part) {
    const row = h('div.dice-row.plain');
    for (const d of part.dice || []) {
      row.append(this.actionable(h('span.die-plain', { class: d.held ? 'held' : '' }, `[${d.value}]`), d.action));
    }
    this.el.append(row);
  }
}

export class MinimalSkin extends Skin {
  static id = 'minimal';
  static label = 'Minimal';
  static blurb = 'Just the game, in characters.';

  constructor() {
    super();
    this.views = { grid: AsciiGridView, dice: PlainDiceView };
  }
}
