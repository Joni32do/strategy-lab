/* DiceView: a row of dice with pips; colored dice for Qwixx, held dice,
 * clickable dice (pick one in Snakes & Ladders), and a roll animation.
 *
 * Part: {view: "dice", dice: [{value, sides, tone, held, action, label}],
 *        fresh} */

import { h, svg } from '../dom.js';
import { View } from './view.js';

const PIPS = {
  1: [[50, 50]],
  2: [[28, 28], [72, 72]],
  3: [[28, 28], [50, 50], [72, 72]],
  4: [[28, 28], [72, 28], [28, 72], [72, 72]],
  5: [[28, 28], [72, 28], [50, 50], [28, 72], [72, 72]],
  6: [[28, 26], [72, 26], [28, 50], [72, 50], [28, 74], [72, 74]],
};

export function dieSvg(value, sides = 6) {
  const root = svg('svg.die-face', { viewBox: '0 0 100 100' });
  root.append(svg('rect.die-body', { x: 4, y: 4, width: 92, height: 92, rx: 20 }));
  if (sides === 6 && PIPS[value]) {
    for (const [x, y] of PIPS[value]) root.append(svg('circle.pip', { cx: x, cy: y, r: 9 }));
  } else {
    root.append(svg('text.die-num', { x: 50, y: 53, 'text-anchor': 'middle', 'dominant-baseline': 'middle' }, String(value)));
  }
  return root;
}

export class DiceView extends View {
  static type = 'dice';

  render(part) {
    const row = h('div.dice-row');
    (part.dice || []).forEach((d, i) => {
      const el = h('div.die', { class: `tone-${d.tone || 'white'}${d.held ? ' held' : ''}${part.fresh ? ' roll' : ''}`,
        style: { animationDelay: `${i * 60}ms` } }, dieSvg(d.value, d.sides || 6));
      if (d.label) el.append(h('span.die-label', d.label));
      row.append(this.actionable(el, d.action));
    });
    this.el.append(row);
  }
}
