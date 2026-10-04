/* Tiny DOM helpers used everywhere.
 *
 *   h('div.card.big', {onclick: fn, title: 'x'}, child, 'text', [more])
 *   svg('circle', {cx: 5, cy: 5, r: 3})
 *
 * Attributes: `class` appends, `style` takes an object, `on<event>` adds a
 * listener, `dataset` merges, `html` sets innerHTML (trusted strings only).
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

function isAttrs(x) {
  return x && typeof x === 'object' && !(x instanceof Node) && !Array.isArray(x);
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false || c === true) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

function applyAttrs(el, attrs, isSvg) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') {
      if (isSvg) el.setAttribute('class', ((el.getAttribute('class') || '') + ' ' + v).trim());
      else el.className = (el.className ? el.className + ' ' : '') + v;
    } else if (k === 'style' && typeof v === 'object') {
      for (const [sk, sv] of Object.entries(v)) {
        if (sk.startsWith('--')) el.style.setProperty(sk, sv);
        else el.style[sk] = sv;
      }
    } else if (k.startsWith('on') && typeof v === 'function') {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k === 'dataset') {
      Object.assign(el.dataset, v);
    } else if (k === 'html') {
      el.innerHTML = v;
    } else if (v === true) {
      el.setAttribute(k, '');
    } else {
      el.setAttribute(k, v);
    }
  }
}

export function h(tag, attrs, ...children) {
  if (!isAttrs(attrs)) { if (attrs !== undefined) children.unshift(attrs); attrs = null; }
  const [name, ...classes] = tag.split('.');
  const el = document.createElement(name || 'div');
  if (classes.length) el.className = classes.join(' ');
  applyAttrs(el, attrs, false);
  append(el, children);
  return el;
}

export function svg(tag, attrs, ...children) {
  if (!isAttrs(attrs)) { if (attrs !== undefined) children.unshift(attrs); attrs = null; }
  const [name, ...classes] = tag.split('.');
  const el = document.createElementNS(SVG_NS, name);
  if (classes.length) el.setAttribute('class', classes.join(' '));
  applyAttrs(el, attrs, true);
  append(el, children);
  return el;
}

export const clear = (el) => { el.replaceChildren(); return el; };
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function debounce(fn, ms) {
  let t = 0;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export function fmt(x, digits = 2) {
  if (x == null || Number.isNaN(x)) return '-';
  if (typeof x !== 'number') return String(x);
  if (Number.isInteger(x)) return String(x);
  return x.toFixed(digits);
}

export const pct = (x, digits = 0) => (x == null ? '-' : `${(x * 100).toFixed(digits)}%`);

/* Probability as a friendly fraction when it is one ("1/6"), else percent. */
export function prob(p) {
  if (p == null) return '-';
  for (const d of [2, 3, 4, 6, 8, 9, 12, 16, 18, 36]) {
    const n = Math.round(p * d);
    if (n > 0 && Math.abs(n / d - p) < 1e-9) {
      const g = gcd(n, d);
      return `${n / g}/${d / g}`;
    }
  }
  return pct(p, p < 0.1 ? 1 : 0);
}

function gcd(a, b) { return b ? gcd(b, a % b) : a; }

export function uid() {
  return (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2)).replace(/-/g, '');
}

export function randomSeed() { return Math.floor(Math.random() * 2147483647); }

/* Local storage that never throws (private mode, quota). */
export const local = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ } },
  remove(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } },
};

export function timeAgo(ts) {
  const s = Math.max(1, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  return d === 1 ? 'yesterday' : `${d} days ago`;
}
