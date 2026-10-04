/* Model lens view: how can this game be described as an MDP, and how is it
 * built (its class lineage)? Result schema: strategy_lab/lenses/model.py. */

import { h } from '../dom.js';
import { icon } from '../icons.js';
import { LensView } from './lens.js';

const BADGE = { true: ['Markov', 'good'], false: ['not Markov', 'bad'], approx: ['approx. Markov', 'warn'] };

export default class ModelLens extends LensView {
  render(r) {
    const b = this.body;
    b.append(h('div.lens-card',
      h('div.upper.muted', 'How this game is built'),
      h('div.lineage', r.lineage.map((name, i) => [
        i ? icon('chevron-right', { cls: 'lineage-sep' }) : null,
        h('code', { class: i === r.lineage.length - 1 ? 'me' : '' }, name)])),
      r.family?.blurb ? h('p.small', h('strong', `${r.family.name}: `), r.family.blurb) : null,
      h('dl.kv.facts', r.facts.flatMap(([k, v]) => [h('dt', k), h('dd', v)]))));

    if (r.legal) {
      const folded = r.classes && r.classes < r.legal;
      b.append(h('div.lens-card',
        h('div.upper.muted', 'Decisions right now'),
        h('div.big-line', folded ? `${r.legal} legal moves \u{2192} ${r.classes} real decisions` : `${r.legal} legal moves`),
        folded ? h('p.small.muted', 'Moves that are rotations or mirrors of each other lead to positions of the same value.') : null));
    }

    if (r.models?.length) {
      const list = h('div.models');
      for (const m of r.models) {
        const [label, tone] = BADGE[String(m.markov)] || BADGE.approx;
        list.append(h('details.model', { open: list.children.length === 0 },
          h('summary', h('strong', m.name), h(`span.badge.tone-${tone}`, label), m.size ? h('span.small.muted', m.size) : null),
          h('dl.kv', [
            ['State', m.state], ['Actions', m.actions], ['Transition', m.transition], ['Reward', m.reward], ['Why / cost', m.note],
          ].filter(([, v]) => v).flatMap(([k, v]) => [h('dt', k), h('dd', v)]))));
      }
      b.append(h('div.lens-card', h('div.upper.muted', 'Ways to describe the state'), list));
    }

    if (r.observation) {
      b.append(h('details.lens-card', h('summary.upper.muted', 'What the engine sees now'), h('pre.lens-json', r.observation)));
    }
  }
}
