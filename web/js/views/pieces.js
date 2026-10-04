/* Piece drawings shared by board views: X, O, discs, tokens, chess glyphs,
 * the RL agent. All SVG, colored by seat via CSS variables. */

import { svg } from '../dom.js';

// Chess symbols as escapes (the source stays ASCII).
const WHITE = { K: '\u{2654}', Q: '\u{2655}', R: '\u{2656}', B: '\u{2657}', N: '\u{2658}', P: '\u{2659}' };
const BLACK = { K: '\u{265A}', Q: '\u{265B}', R: '\u{265C}', B: '\u{265D}', N: '\u{265E}', P: '\u{265F}' };

export function pieceSvg(p) {
  const color = p.owner == null ? 'var(--text-2)' : `var(--p${p.owner % 6})`;
  const root = svg('svg.piece', { viewBox: '0 0 100 100', class: `shape-${p.shape || 'token'}` });
  root.style.setProperty('--pc', color);
  switch (p.shape) {
    case 'x':
      root.append(svg('path.stroke', { d: 'M24 24 L76 76 M76 24 L24 76' }));
      break;
    case 'o':
      root.append(svg('circle.stroke', { cx: 50, cy: 50, r: 27 }));
      break;
    case 'disc':
      root.append(svg('circle.fill', { cx: 50, cy: 50, r: 40 }));
      root.append(svg('circle.inner', { cx: 50, cy: 50, r: 28 }));
      break;
    case 'glyph': {
      const g = p.glyph || '?';
      const upper = g === g.toUpperCase();
      const sym = (upper ? WHITE : BLACK)[g.toUpperCase()] || g;
      root.append(svg('text.glyph', { x: 50, y: 54, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
        class: upper ? 'white' : 'black' }, sym));
      break;
    }
    case 'agent':
      root.append(svg('circle.fill', { cx: 50, cy: 52, r: 34 }));
      root.append(svg('circle.eye', { cx: 39, cy: 46, r: 6 }));
      root.append(svg('circle.eye', { cx: 61, cy: 46, r: 6 }));
      root.append(svg('path.mouth', { d: 'M38 63 Q50 72 62 63' }));
      break;
    default:
      root.append(svg('circle.fill', { cx: 50, cy: 50, r: 30 }));
      root.append(svg('circle.shine', { cx: 41, cy: 41, r: 9 }));
  }
  if (p.label) {
    root.append(svg('text.piece-label', { x: 50, y: 56, 'text-anchor': 'middle' }, p.label));
  }
  return root;
}

const ARROWS = { up: 0, right: 90, down: 180, left: 270 };

export function arrowSvg(dir) {
  const root = svg('svg.arrow', { viewBox: '0 0 100 100' });
  root.append(svg('path', {
    d: 'M50 18 L74 50 L58 50 L58 82 L42 82 L42 50 L26 50 Z',
    transform: `rotate(${ARROWS[dir] ?? 0} 50 50)`,
  }));
  return root;
}
