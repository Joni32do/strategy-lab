/* Paper: a notebook look. Boards are drawn by hand: SketchGridView extends
 * the stock GridView and only replaces how lines and pieces are drawn. */

import { svg } from '../dom.js';
import { GridView } from '../views/grid.js';
import { DiceView } from '../views/dice.js';
import { Skin } from './skin.js';

/* A wobbly pen line from (x1, y1) to (x2, y2), deterministic per seed. */
function penPath(x1, y1, x2, y2, seed) {
  let s = seed * 9301 + 49297;
  const rnd = () => { s = (s * 9301 + 49297) % 233280; return s / 233280 - 0.5; };
  const mx = (x1 + x2) / 2 + rnd() * 1.6;
  const my = (y1 + y2) / 2 + rnd() * 1.6;
  return `M${x1 + rnd()},${y1 + rnd()} Q${mx},${my} ${x2 + rnd()},${y2 + rnd()}`;
}

export class SketchGridView extends GridView {
  static type = 'grid';

  render(part) {
    if (part.style !== 'board') { super.render(part); return; }
    super.render(part);
    // replace the CSS cell borders with pen strokes on the overlay layer
    const board = this.el.querySelector('.grid-board');
    board.classList.add('sketch');
    const layer = board.querySelector('.grid-layer');
    const W = part.cols * 10;
    const H = part.rows * 10;
    for (let c = 1; c < part.cols; c++) {
      layer.prepend(svg('path.pen', { d: penPath(c * 10, 1, c * 10, H - 1, c) }));
    }
    for (let r = 1; r < part.rows; r++) {
      layer.prepend(svg('path.pen', { d: penPath(1, r * 10, W - 1, r * 10, r + 17) }));
    }
  }
}

export class PaperDiceView extends DiceView {
  static type = 'dice';

  render(part) {
    super.render(part);
    this.el.querySelectorAll('.die').forEach((d, i) => {
      d.style.transform = `rotate(${((i * 37) % 11) - 5}deg)`;
    });
  }
}

export class PaperSkin extends Skin {
  static id = 'paper';
  static label = 'Paper';
  static blurb = 'A squared notebook and a pen.';

  constructor() {
    super();
    this.views = { grid: SketchGridView, dice: PaperDiceView };
  }
}

