/* View: the base class of everything that draws a scene part.
 *
 * A game's scene (see strategy_lab/core/scene.py) is a list of parts like
 * {view: "grid", rows: 3, cols: 3, cells: [...]}. The registry picks the
 * View subclass for part.view; the skin may swap in its own subclass.
 *
 * Subclasses implement render(part) and build DOM inside this.el. Two
 * conventions make every board interactive and annotatable for free:
 *
 *   this.actionable(el, a)   el plays action a when clicked (human turn)
 *   lens overlays            {actions: {"<a>": {text, tone}}} put a badge on
 *                            every element that plays that action
 */

import { clear, h } from '../dom.js';

export class View {
  static type = 'base';

  /** @param ctx {onAction(a), interactive(): bool, viewer, names: [], skin} */
  constructor(ctx) {
    this.ctx = ctx;
    this.part = null;
    this.overlay = null;
    this.el = h(`div.view.view-${this.constructor.type}`);
  }

  /** Draw `part` into this.el. Override. */
  render(part) {
    this.el.append(h('pre', JSON.stringify(part, null, 1)));
  }

  /** Called with every new part. Default: redraw everything. */
  update(part) {
    const prev = this.part === part ? null : this.part;
    this.part = part;
    clear(this.el);
    if (part.caption) this.el.append(h('div.view-caption', part.caption));
    this.render(part, prev);
    this.wire();
    this.annotate(this.overlay);
  }

  /** Mark `el` as playing action `a` (null leaves it inert). */
  actionable(el, a) {
    if (a === undefined || a === null) return el;
    el.dataset.action = JSON.stringify(a);
    el.classList.add('actionable');
    el.setAttribute('role', 'button');
    el.tabIndex = 0;
    return el;
  }

  wire() {
    for (const el of this.el.querySelectorAll('[data-action]')) {
      const fire = (ev) => {
        ev.stopPropagation();
        if (!this.ctx.interactive()) return;
        this.ctx.onAction(JSON.parse(el.dataset.action));
      };
      el.addEventListener('click', fire);
      el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') fire(ev); });
    }
  }

  /** Put lens badges on actionable elements. */
  annotate(overlay) {
    this.overlay = overlay;
    for (const old of this.el.querySelectorAll('.ov')) old.remove();
    for (const el of this.el.querySelectorAll('.ov-host')) el.classList.remove('ov-host', 'ov-best', 'ov-bad');
    const acts = overlay?.actions;
    if (!acts) return;
    const seen = new Set();   // one badge per action, even if two elements play it
    for (const el of this.el.querySelectorAll('[data-action]')) {
      const key = String(JSON.parse(el.dataset.action));
      const o = acts[key];
      if (!o || seen.has(key)) continue;
      seen.add(key);
      el.classList.add('ov-host');
      if (o.tone === 'best') el.classList.add('ov-best');
      if (o.tone === 'bad') el.classList.add('ov-bad');
      el.append(h(`span.ov.tone-${o.tone || 'neutral'}`, o.text ?? ''));
    }
  }

  /** Player color for a seat. */
  color(owner) { return owner == null ? 'var(--muted)' : `var(--p${owner % 6})`; }

  name(seat) { return this.ctx.names?.[seat] ?? `Player ${seat + 1}`; }
}
