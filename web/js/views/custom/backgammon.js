/* BackgammonView: the board, bar and trays as SVG, plus a clickable list of
 * the legal moves under it (scene part "backgammon", emitted by
 * strategy_lab/games/backgammon.py; schema in its module docstring).
 *
 * Hovering a move draws arrows for each checker it moves. Seat 0 (X) moves
 * from position 0 up to 23 and bears off at the top right; seat 1 (O) moves
 * down and bears off at the bottom right. */

import { h, svg } from '../../dom.js';
import { View } from '../view.js';
import { registerView } from '../registry.js';

const COL_W = 28;
const LEFT = 8;
const BAR_W = 26;
const TOP = 8;
const HEIGHT = 250;
const POINT_H = 100;
const R = 11;
const TRAY_X = LEFT + 12 * COL_W + BAR_W + 10;
const WIDTH = TRAY_X + 36;
const MID_X = LEFT + 6 * COL_W + BAR_W / 2;

function colX(col) { return LEFT + col * COL_W + (col >= 6 ? BAR_W : 0) + COL_W / 2; }

export class BackgammonView extends View {
  static type = 'backgammon';

  render(part) {
    const root = svg('svg.bg-board', { viewBox: `0 0 ${WIDTH} ${HEIGHT + 2 * TOP}` });
    root.append(svg('rect.bg-frame', { x: 0, y: 0, width: WIDTH, height: HEIGHT + 2 * TOP, rx: 12 }));
    root.append(svg('rect.bg-bar', { x: LEFT + 6 * COL_W, y: TOP, width: BAR_W, height: HEIGHT }));
    this.slot = new Map();
    const byPos = new Map(part.points.map((p) => [p.pos, p]));
    ['top', 'bottom'].forEach((row) => {
      part.layout[row].forEach((pos, col) => {
        const top = row === 'top';
        const x = colX(col);
        const y0 = top ? TOP : TOP + HEIGHT;
        const y1 = top ? TOP + POINT_H + 20 : TOP + HEIGHT - POINT_H - 20;
        root.append(svg(`polygon.bg-point.pt-${(col + (top ? 1 : 0)) % 2 ? 'a' : 'b'}`,
          { points: `${x - COL_W / 2 + 1},${y0} ${x + COL_W / 2 - 1},${y0} ${x},${y1}` }));
        this.slot.set(pos, { x, y: top ? TOP + 40 : TOP + HEIGHT - 40 });
        this.stack(root, byPos.get(pos), x, y0, top ? 1 : -1);
      });
    });
    for (const seat of [0, 1]) this.barAndTray(root, part, seat);
    this.arrows = svg('g.bg-arrows');
    root.append(this.arrows);
    this.el.append(root, this.pipLine(part));
    if (part.moves?.length) this.el.append(this.moveList(part));
  }

  checker(x, y, owner) {
    return svg('circle.bg-checker', { cx: x, cy: y, r: R, style: { fill: this.color(owner) } });
  }

  /* Up to five checkers; the fifth carries the total when there are more. */
  stack(root, p, x, y0, dir) {
    if (!p || !p.n) return;
    const shown = Math.min(5, p.n);
    for (let i = 0; i < shown; i++) {
      const y = y0 + dir * (R + 1 + i * (2 * R - 2));
      root.append(this.checker(x, y, p.owner));
      if (i === shown - 1 && p.n > 5) {
        root.append(svg('text.bg-count', { x, y, 'text-anchor': 'middle', 'dominant-baseline': 'central' }, String(p.n)));
      }
    }
  }

  barAndTray(root, part, seat) {
    const dir = seat === 0 ? 1 : -1;
    const y0 = seat === 0 ? TOP + 6 : TOP + HEIGHT - 6;
    const bar = part.bar[seat];
    for (let i = 0; i < Math.min(bar, 4); i++) root.append(this.checker(MID_X, y0 + dir * (R + i * (2 * R - 2)), seat));
    if (bar > 4) {
      root.append(svg('text.bg-count', { x: MID_X, y: y0 + dir * (R + 3 * (2 * R - 2)), 'text-anchor': 'middle', 'dominant-baseline': 'central' }, String(bar)));
    }
    const ty = seat === 0 ? TOP : TOP + HEIGHT / 2 + 4;
    root.append(svg('rect.bg-tray', { x: TRAY_X, y: ty, width: 26, height: HEIGHT / 2 - 4, rx: 6 }));
    const off = part.off[seat];
    for (let i = 0; i < off; i++) {
      const y = seat === 0 ? ty + 4 + i * 5.5 : ty + HEIGHT / 2 - 12 - i * 5.5;
      root.append(svg('rect.bg-off', { x: TRAY_X + 3, y, width: 20, height: 4.2, rx: 1.5, style: { fill: this.color(seat) } }));
    }
    this.slot.set(`bar${seat}`, { x: MID_X, y: seat === 0 ? TOP + 40 : TOP + HEIGHT - 40 });
    this.slot.set(`off${seat}`, { x: TRAY_X + 13, y: ty + HEIGHT / 4 });
  }

  pipLine(part) {
    const row = h('div.bg-pips');
    for (const seat of [0, 1]) {
      row.append(h('span.bg-pip', { class: part.turn === seat ? 'turn' : '' },
        h('i', { style: { background: this.color(seat) } }), `${this.name(seat)}: `,
        h('b.num', String(part.pips[seat])), ' pips, ', h('b.num', String(part.off[seat])), ' off',
        part.bar[seat] ? `, ${part.bar[seat]} on the bar` : ''));
    }
    return row;
  }

  moveList(part) {
    const wrap = h('div.bg-moves', h('div.upper.muted', 'Your moves'));
    const list = h('div.bg-move-list');
    for (const m of part.moves) {
      const chip = this.actionable(h('button.bg-move', m.label), m.action);
      chip.addEventListener('mouseenter', () => this.showSteps(m, part.turn));
      chip.addEventListener('mouseleave', () => this.arrows.replaceChildren());
      list.append(chip);
    }
    wrap.append(list);
    return wrap;
  }

  showSteps(move, seat) {
    this.arrows.replaceChildren();
    for (const s of move.steps) {
      const a = this.slot.get(s.from === 'bar' ? `bar${seat}` : s.from);
      const b = this.slot.get(s.to === 'off' ? `off${seat}` : s.to);
      if (!a || !b) continue;
      const hit = s.hit ? '.hit' : '';
      this.arrows.append(svg(`line.bg-arrow${hit}`, { x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
      this.arrows.append(svg(`circle.bg-arrow-end${hit}`, { cx: b.x, cy: b.y, r: 4 }));
    }
  }
}

registerView(BackgammonView);
