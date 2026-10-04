/* CartPoleView: a track, a cart and a pole at angle theta (scene part
 * "cartpole", emitted by strategy_lab/games/cartpole.py).
 *
 * The scene tints toward red as the cart nears the end of the track or the
 * pole nears its fall angle, so the two failure conditions are visible. */

import { h, svg } from '../../dom.js';
import { View } from '../view.js';
import { registerView } from '../registry.js';

const W = 480;
const H = 220;
const GROUND = 168;
const TRACK = 190;
const POLE = 92;
const DEG = 180 / Math.PI;

export class CartPoleView extends View {
  static type = 'cartpole';

  render(part) {
    const { x, theta, xLimit, thetaLimit } = part;
    const danger = Math.max(Math.abs(x) / xLimit, Math.abs(theta) / thetaLimit);
    const level = part.done ? 'dead' : danger > 0.85 ? 'high' : danger > 0.6 ? 'mid' : 'ok';
    const cx = W / 2 + (x / xLimit) * TRACK;
    const root = svg(`svg.cp-scene.danger-${level}`, { viewBox: `0 0 ${W} ${H}` });
    root.append(svg('rect.cp-sky', { x: 0, y: 0, width: W, height: H, rx: 14 }));
    root.append(svg('rect.cp-tint', { x: 0, y: 0, width: W, height: H, rx: 14, style: { opacity: Math.min(1, danger * danger).toFixed(2) } }));
    for (const side of [-1, 1]) {
      const lx = W / 2 + side * TRACK;
      root.append(svg('line.cp-limit', { x1: lx, y1: GROUND - 120, x2: lx, y2: GROUND + 8 }));
      root.append(svg('text.cp-limit-text', { x: lx, y: GROUND + 26, 'text-anchor': 'middle' }, `${side * xLimit}`));
    }
    root.append(svg('line.cp-track', { x1: W / 2 - TRACK, y1: GROUND, x2: W / 2 + TRACK, y2: GROUND }));
    root.append(svg('line.cp-center', { x1: W / 2, y1: GROUND, x2: W / 2, y2: GROUND + 8 }));
    const cart = svg('g.cp-cart', { transform: `translate(${cx.toFixed(1)} ${GROUND})` });
    cart.append(svg('rect.cp-body', { x: -30, y: -22, width: 60, height: 22, rx: 5 }));
    cart.append(svg('circle.cp-wheel', { cx: -18, cy: 0, r: 6 }), svg('circle.cp-wheel', { cx: 18, cy: 0, r: 6 }));
    const pole = svg('g.cp-pole', { transform: `translate(0 -22) rotate(${(theta * DEG).toFixed(2)})` });
    pole.append(svg('line.cp-stick', { x1: 0, y1: 0, x2: 0, y2: -POLE }));
    pole.append(svg('circle.cp-top', { cx: 0, cy: -POLE, r: 6 }));
    pole.append(svg('circle.cp-pivot', { cx: 0, cy: 0, r: 3.5 }));
    cart.append(pole);
    root.append(cart);
    this.el.append(root, h('div.cp-stats',
      h('span.cp-stat', h('b.num', String(part.steps)), ' steps'),
      h('span.cp-stat', 'angle ', h('b.num', `${(theta * DEG).toFixed(1)}\u{B0}`), ` of \u{B1}${(thetaLimit * DEG).toFixed(0)}\u{B0}`),
      h('span.cp-stat', 'position ', h('b.num', x.toFixed(2)), ` of \u{B1}${xLimit}`),
      part.done ? h('span.cp-stat.over', 'episode over') : null));
  }
}

registerView(CartPoleView);
