/* Text rendering: a very small Markdown subset and KaTeX math.
 *
 * Markdown: paragraphs, - lists, **bold**, *italic*, `code`, and inline
 * math between $...$. Concept cards and rulebooks use only this. */

import { h } from './dom.js';

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function mathHtml(tex, display = false) {
  if (window.katex) {
    try {
      return window.katex.renderToString(tex, { displayMode: display, throwOnError: false });
    } catch { /* fall through */ }
  }
  return `<code>${escapeHtml(tex)}</code>`;
}

function inline(s) {
  const parts = [];
  // pull out math first so * and _ inside formulas survive
  const re = /\$([^$]+)\$/g;
  let last = 0;
  let m;
  while ((m = re.exec(s))) {
    parts.push({ t: s.slice(last, m.index) });
    parts.push({ math: m[1] });
    last = m.index + m[0].length;
  }
  parts.push({ t: s.slice(last) });
  return parts.map((p) => {
    if (p.math) return mathHtml(p.math);
    return escapeHtml(p.t)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>');
  }).join('');
}

export function markdownHtml(src) {
  const blocks = String(src || '').trim().split(/\n\s*\n/);
  return blocks.map((b) => {
    const lines = b.split('\n');
    if (lines.every((l) => /^\s*[-*] /.test(l))) {
      return '<ul>' + lines.map((l) => `<li>${inline(l.replace(/^\s*[-*] /, ''))}</li>`).join('') + '</ul>';
    }
    if (lines.every((l) => /^\s*\d+\. /.test(l))) {
      return '<ol>' + lines.map((l) => `<li>${inline(l.replace(/^\s*\d+\. /, ''))}</li>`).join('') + '</ol>';
    }
    return `<p>${inline(lines.join(' '))}</p>`;
  }).join('');
}

export function md(src, cls = 'md') { return h(`div.${cls}`, { html: markdownHtml(src) }); }

export function math(tex, display = true) {
  return h(display ? 'div.math' : 'span.math', { html: mathHtml(tex, display) });
}

/* KaTeX loads with `defer`; re-render placeholders once it is there. */
export function whenKatex() {
  return new Promise((resolve) => {
    if (window.katex) return resolve();
    const t = setInterval(() => { if (window.katex) { clearInterval(t); resolve(); } }, 50);
    setTimeout(() => { clearInterval(t); resolve(); }, 4000);
  });
}
