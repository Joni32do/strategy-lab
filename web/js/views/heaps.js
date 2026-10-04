/* HeapsView: piles of sticks (Nim). Hover a stick to preview taking it and
 * everything to its right; click to take.
 *
 * Part: {view: "heaps", heaps: [{count, label, actions: [take1, take2, ...]}]} */

import { h } from '../dom.js';
import { View } from './view.js';

export class HeapsView extends View {
  static type = 'heaps';

  render(part) {
    const box = h('div.heaps');
    for (const heap of part.heaps) {
      const row = h('div.heap');
      row.append(h('div.heap-label', heap.label || ''), h('div.heap-count.num', String(heap.count)));
      const sticks = h('div.heap-sticks');
      for (let i = 0; i < heap.count; i++) {
        const take = heap.count - i;
        const a = heap.actions?.[take - 1];
        const stick = h('span.stick', { title: a == null ? '' : `take ${take}` });
        if (a != null) {
          this.actionable(stick, a);
          stick.addEventListener('mouseenter', () => mark(sticks, i, true));
          stick.addEventListener('mouseleave', () => mark(sticks, i, false));
        }
        sticks.append(stick);
      }
      if (!heap.count) sticks.append(h('span.heap-empty', 'empty'));
      row.append(sticks);
      box.append(row);
    }
    this.el.append(box);
  }
}

function mark(sticks, from, on) {
  [...sticks.children].forEach((s, j) => s.classList.toggle('taking', on && j >= from));
}
