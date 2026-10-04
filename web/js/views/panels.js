/* Small generic views: bars, key/value tables, choice buttons, text.
 *
 *   {view: "bars", items: [{label, value, max, min, tone, text}]}
 *   {view: "kv", items: [[label, value]], owner}
 *   {view: "buttons", choices: [{action, label, sub}]}
 *   {view: "text", text, mono} */

import { h } from '../dom.js';
import { View } from './view.js';

export class BarsView extends View {
  static type = 'bars';

  render(part) {
    const box = h('div.bars');
    for (const it of part.items) {
      const lo = it.min ?? 0;
      const hi = it.max ?? Math.max(1, ...part.items.map((x) => Math.abs(x.value)));
      const frac = Math.max(0, Math.min(1, (it.value - lo) / ((hi - lo) || 1)));
      const tone = it.tone?.startsWith('p') ? `var(--${it.tone})` : null;
      box.append(h('div.bar', { class: it.tone ? `tone-${it.tone}` : '' },
        h('span.bar-label', it.label),
        h('span.bar-track', h('span.bar-fill', { style: { width: `${frac * 100}%`, background: tone } })),
        h('span.bar-text.num', it.text ?? String(it.value))));
    }
    this.el.append(box);
  }
}

export class KvView extends View {
  static type = 'kv';

  render(part) {
    const t = h('dl.kv');
    if (part.owner != null) t.style.setProperty('--owner', this.color(part.owner));
    for (const [k, v] of part.items) t.append(h('dt', k), h('dd', String(v)));
    this.el.append(t);
  }
}

export class ButtonsView extends View {
  static type = 'buttons';

  render(part) {
    const row = h('div.choices');
    for (const c of part.choices || []) {
      row.append(this.actionable(h('div.choice', h('span.choice-label', c.label),
        c.sub ? h('span.choice-sub', c.sub) : null), c.action));
    }
    this.el.append(row);
  }
}

export class TextView extends View {
  static type = 'text';

  render(part) {
    this.el.append(part.mono ? h('pre.text-mono', part.text) : h('p.text-plain', part.text));
  }
}
