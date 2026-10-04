/* ArmsView: slot machines with running statistics (multi-armed bandits).
 *
 * Part: {view: "arms", arms: [{label, pulls, mean, action, tone, sub}]} */

import { h } from '../dom.js';
import { icon } from '../icons.js';
import { View } from './view.js';

export class ArmsView extends View {
  static type = 'arms';

  render(part) {
    const grid = h('div.arms');
    for (const a of part.arms) {
      const mean = a.mean == null ? null : Math.max(0, Math.min(1, a.mean));
      const el = h('div.arm', { class: a.tone ? `tone-${a.tone}` : '' },
        h('div.arm-top', icon('slot'), h('span.arm-label', a.label)),
        h('div.arm-meter', h('span', { style: { height: `${(mean ?? 0) * 100}%` } })),
        h('div.arm-mean.num', mean == null ? '?' : mean.toFixed(2)),
        h('div.arm-pulls.small.muted', `${a.pulls} pull${a.pulls === 1 ? '' : 's'}`),
        a.sub ? h('div.arm-sub.tiny', a.sub) : null);
      grid.append(this.actionable(el, a.action));
    }
    this.el.append(grid);
  }
}
