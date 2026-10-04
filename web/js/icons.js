/* Icons by name (web/assets/icons.json, built by scripts/build_icons.py
 * from the Lucide set). Games name their icon in Python: `icon = "dice"`. */

const NS = 'http://www.w3.org/2000/svg';
let ICONS = {};

export async function loadIcons() {
  try {
    ICONS = await (await fetch('assets/icons.json')).json();
  } catch {
    ICONS = {};
  }
}

export function hasIcon(name) { return Boolean(ICONS[name]); }

export function icon(name, opts = {}) {
  const el = document.createElementNS(NS, 'svg');
  el.setAttribute('viewBox', '0 0 24 24');
  el.setAttribute('fill', 'none');
  el.setAttribute('stroke', 'currentColor');
  el.setAttribute('stroke-width', opts.stroke || 2);
  el.setAttribute('stroke-linecap', 'round');
  el.setAttribute('stroke-linejoin', 'round');
  el.setAttribute('aria-hidden', 'true');
  el.setAttribute('class', `icon ${opts.cls || ''}`.trim());
  if (opts.size) { el.setAttribute('width', opts.size); el.setAttribute('height', opts.size); }
  el.innerHTML = ICONS[name] || ICONS.puzzle || '';
  return el;
}
