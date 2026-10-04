/* LensView: the base class of the analysis panels next to the board.
 *
 * Each Python lens (strategy_lab/lenses/<id>.py) has a view here in
 * lenses/<id>.js exporting `default class extends LensView`. Without one,
 * this base class shows the raw result, which is enough while you build a
 * lens.
 *
 * Lifecycle: the game page calls mount() once, then refresh() whenever the
 * position changes (if `auto`), or the user presses Run. render(result)
 * draws the result; result.overlay (if any) is shown on the board. */

import { clear, h, local } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';

export class LensView {
  /** Re-run automatically when the position changes. */
  static auto = true;

  constructor(page, meta) {
    this.page = page;
    this.meta = meta;
    this.result = null;
    this.busy = false;
    this.el = h(`section.lens.lens-${meta.id}`);
    const saved = local.get(this.storeKey(), {});
    this.options = {};
    for (const o of meta.options || []) this.options[o.name] = saved[o.name] ?? o.default;
  }

  storeKey() { return `lab.lens.${this.page.id}.${this.meta.id}`; }

  get auto() { return this.constructor.auto; }

  mount() {
    clear(this.el);
    const concepts = (this.meta.concepts || []).map((c) =>
      h('button.chip.concept-chip', { onclick: () => this.page.openConcept(c) }, icon('cheatsheet'), conceptName(c)));
    this.head = h('header.lens-head',
      h('div.lens-title', icon(this.meta.icon), h('h3', this.meta.title)),
      h('p.lens-blurb', this.meta.blurb),
      concepts.length ? h('div.row.wrap.lens-concepts', concepts) : null);
    this.optsEl = h('div.lens-options');
    this.drawOptions();
    this.body = h('div.lens-body', h('div.empty', 'Make a move or press Run.'));
    this.el.append(this.head, this.optsEl, this.body);
    return this.el;
  }

  drawOptions() {
    clear(this.optsEl);
    const opts = (this.meta.options || []).filter((o) => !o.hidden);
    for (const o of opts) this.optsEl.append(this.optionInput(o));
    if (!this.auto || opts.length) {
      this.optsEl.append(h('button.btn.small.primary', { onclick: () => this.refresh(true) },
        icon('play'), this.runLabel()));
    }
  }

  runLabel() { return 'Run'; }

  optionInput(o) {
    const set = (v) => {
      this.options[o.name] = v;
      local.set(this.storeKey(), this.options);
      if (this.auto) this.refresh(true);
    };
    let input;
    if (o.type === 'bool') {
      input = h('input', { type: 'checkbox', checked: Boolean(this.options[o.name]), onchange: (e) => set(e.target.checked) });
      return h('label.toggle.small', input, o.label);
    }
    if (o.type === 'choice') {
      input = h('select', { onchange: (e) => set(e.target.value) },
        (o.choices || []).map((c) => h('option', { value: c, selected: c === this.options[o.name] }, c)));
    } else {
      input = h('input', { type: 'number', value: this.options[o.name], min: o.min, max: o.max, step: o.step || (o.type === 'int' ? 1 : 0.01),
        onchange: (e) => set(o.type === 'int' ? parseInt(e.target.value, 10) : parseFloat(e.target.value)) });
    }
    return h('label.field.lens-opt', h('span', o.label || o.name), input);
  }

  /** Options sent to the server. Subclasses may add their own state. */
  requestOptions() { return { ...this.options }; }

  async refresh(force = false) {
    if (this.busy) { this.again = true; return; }
    if (!force && !this.auto) return;
    this.busy = true;
    this.el.classList.add('busy');
    try {
      const res = await this.page.runLens(this.meta.id, this.requestOptions());
      this.result = res;
      clear(this.body);
      this.render(res);
      this.page.setOverlay(res.overlay || null);
    } catch (e) {
      clear(this.body);
      this.body.append(h('div.lens-error', icon('info'), e.message));
    } finally {
      this.busy = false;
      this.el.classList.remove('busy');
      if (this.again) { this.again = false; this.refresh(); }
    }
  }

  /** Draw a result. Default: an indented view of the JSON. */
  render(result) {
    const { overlay, ...rest } = result || {};
    this.body.append(h('pre.lens-json', JSON.stringify(rest, null, 2)));
  }

  /** The board changed (new position). */
  positionChanged() { if (this.auto) this.refresh(); }

  unmount() { this.page.setOverlay(null); }
}

/* The concept card's title if the cheatsheet is loaded, else a readable id. */
export function conceptName(id) {
  const c = store.concepts?.concepts?.find((x) => x.id === id);
  return c ? c.title : id.replace(/-/g, ' ').replace(/^./, (ch) => ch.toUpperCase());
}
