/* HexView: the Catan board as SVG (scene part "hex", emitted by
 * strategy_lab/games/catan/game.py; schema in its module docstring).
 *
 * Layers, bottom to top: sea, tiles + number tokens, ports with docks,
 * clickable tiles (robber), roads, free road spots, buildings, free node
 * spots, the robber, and small labeled buttons for tiles with several
 * choices (whom to steal from). Everything clickable goes through
 * this.actionable(); free spots are drawn only while it is your turn. */

import { svg } from '../../dom.js';
import { View } from '../view.js';
import { registerView } from '../registry.js';

const RES_LABEL = { WOOD: 'wood', BRICK: 'brick', SHEEP: 'sheep', WHEAT: 'wheat', ORE: 'ore' };
const HOUSE = (x, y) => `${x - 2},${y + 1.6} ${x - 2},${y - 0.4} ${x},${y - 2.2} ${x + 2},${y - 0.4} ${x + 2},${y + 1.6}`;
const CITY = (x, y) => `${x - 3},${y + 2} ${x - 3},${y - 1} ${x - 1},${y - 1} ${x - 1},${y - 3} ${x + 0.5},${y - 4.2} ${x + 2},${y - 3} ${x + 2},${y - 1} ${x + 3},${y - 1} ${x + 3},${y + 2}`;

export class HexView extends View {
  static type = 'hex';

  render(part) {
    const pad = 3;
    const root = svg('svg.hex-board', { viewBox: `${-pad} ${-pad} ${part.width + 2 * pad} ${part.height + 2 * pad}` });
    root.append(svg('rect.hex-sea', { x: -pad, y: -pad, width: part.width + 2 * pad, height: part.height + 2 * pad, rx: 6 }));
    const corner = new Map();
    for (const t of part.tiles) t.nodes?.forEach((n, i) => corner.set(n, t.points[i]));
    this.layer(root, 'hex-tiles', part.tiles.map((t) => this.tile(t)));
    this.layer(root, 'hex-ports', part.ports.map((p) => this.port(p, corner)));
    this.layer(root, 'hex-tile-hits', part.tiles.filter((t) => t.action != null).map((t) => this.tileHit(t)));
    this.layer(root, 'hex-roads', part.edges.filter((e) => e.owner != null).map((e) => this.road(e)));
    this.layer(root, 'hex-road-spots', part.edges.filter((e) => e.action != null).map((e) => this.roadSpot(e)));
    this.layer(root, 'hex-buildings', part.nodes.filter((n) => n.kind).map((n) => this.building(n)));
    this.layer(root, 'hex-node-spots', part.nodes.filter((n) => n.action != null).map((n) => this.nodeSpot(n)));
    this.layer(root, 'hex-robber', part.tiles.filter((t) => t.robber).map((t) => this.robber(t)));
    this.layer(root, 'hex-choices', part.tiles.filter((t) => t.actions?.length > 1).map((t) => this.choices(t)));
    this.el.append(root);
  }

  layer(root, cls, items) {
    const g = svg(`g.${cls}`);
    g.append(...items);
    root.append(g);
  }

  tile(t) {
    const g = svg('g.hex-tile');
    g.append(svg(`polygon.hex-land.res-${t.resource || 'DESERT'}`, { points: t.points.map((p) => p.join(',')).join(' ') }));
    if (t.number) {
      const hot = t.number === 6 || t.number === 8;
      g.append(svg('circle.hex-token', { cx: t.cx, cy: t.cy, r: 3.8 }));
      g.append(svg(`text.hex-number${hot ? '.hot' : ''}`, { x: t.cx, y: t.cy - 0.5, 'text-anchor': 'middle', 'dominant-baseline': 'central' }, String(t.number)));
      const pips = 6 - Math.abs(7 - t.number);
      for (let i = 0; i < pips; i++) {
        g.append(svg(`circle.hex-pip${hot ? '.hot' : ''}`, { cx: t.cx + (i - (pips - 1) / 2) * 0.95, cy: t.cy + 2.4, r: 0.36 }));
      }
    }
    return g;
  }

  port(p, corner) {
    const g = svg('g.hex-port');
    for (const n of p.nodes) {
      const c = corner.get(n);
      if (c) g.append(svg('line.hex-dock', { x1: p.x, y1: p.y, x2: c[0], y2: c[1] }));
    }
    g.append(svg(`circle.hex-port-badge.res-${p.resource || 'ANY'}`, { cx: p.x, cy: p.y, r: 3.1 }));
    g.append(svg('text.hex-port-text', { x: p.x, y: p.y - 0.5, 'text-anchor': 'middle', 'dominant-baseline': 'central' }, `${p.ratio}:1`));
    if (p.resource) g.append(svg('text.hex-port-res', { x: p.x, y: p.y + 4.6, 'text-anchor': 'middle' }, RES_LABEL[p.resource]));
    return g;
  }

  tileHit(t) {
    const hit = svg('polygon.hex-tile-hit', { points: t.points.map((p) => p.join(',')).join(' ') });
    return this.actionable(hit, t.action);
  }

  road(e) {
    const g = svg('g.hex-road');
    g.append(svg('line.hex-road-edge', { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2 }));
    g.append(svg('line.hex-road-line', { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2, style: { stroke: this.color(e.owner) } }));
    return g;
  }

  roadSpot(e) {
    const g = svg('g.hex-spot');
    g.append(svg('line.hex-spot-line', { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2 }));
    g.append(this.actionable(svg('line.hex-hit', { x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2 }), e.action));
    return g;
  }

  building(n) {
    const pts = n.kind === 'city' ? CITY(n.x, n.y) : HOUSE(n.x, n.y);
    return svg(`polygon.hex-building.${n.kind}`, { points: pts, style: { fill: this.color(n.owner) } });
  }

  nodeSpot(n) {
    const g = svg('g.hex-spot');
    g.append(svg('circle.hex-spot-ring', { cx: n.x, cy: n.y, r: n.kind ? 4.2 : 2.3 }));
    g.append(this.actionable(svg('circle.hex-hit', { cx: n.x, cy: n.y, r: 3.8 }), n.action));
    return g;
  }

  robber(t) {
    const x = t.number ? t.cx + 5.2 : t.cx;
    const y = t.number ? t.cy + 3.6 : t.cy + 1;
    const g = svg('g.hex-robber-pawn');
    g.append(svg('circle', { cx: x, cy: y - 2.6, r: 1.5 }));
    g.append(svg('path', { d: `M${x - 2.4},${y + 2.6} Q${x},${y - 3} ${x + 2.4},${y + 2.6} Z` }));
    return g;
  }

  /* Several things can happen on this tile (steal from A or from B): one
   * small button per choice, stacked on the tile. */
  choices(t) {
    const g = svg('g.hex-choice-group');
    const n = t.actions.length;
    t.actions.forEach((a, i) => {
      const text = a.label.replace('steal from ', 'steal ');
      const w = text.length * 1.15 + 2.6;
      const y = t.cy + (t.number ? 4.6 : 0) + i * 3.7 - (t.number ? 0 : ((n - 1) * 3.7) / 2);
      const b = svg('g.hex-choice');
      b.append(svg('rect', { x: t.cx - w / 2, y: y - 1.6, width: w, height: 3.3, rx: 1.6 }));
      b.append(svg('text', { x: t.cx, y, 'text-anchor': 'middle', 'dominant-baseline': 'central' }, text));
      g.append(this.actionable(b, a.action));
    });
    return g;
  }
}

registerView(HexView);
