/* CardsView: a card table seen from the viewer's seat (trick-taking games,
 * poker). The viewer sits at the bottom; others fan around the table.
 *
 * Part: {view: "cards", seat, names, hand: [card], handSizes, trick:
 *        [{seat, card}], leader, toAct, lastTrick, taken, badges, center}
 * card: {rank, suit: C|S|H|D, action, trump, points, faceup} */

import { h } from '../dom.js';
import { View } from './view.js';

const SUITS = { C: '\u{2663}', S: '\u{2660}', H: '\u{2665}', D: '\u{2666}' };
const RED = new Set(['H', 'D']);

export function cardEl(c, extra = '') {
  if (c.faceup === false) return h('div.pcard.back', { class: extra });
  return h('div.pcard', { class: `${RED.has(c.suit) ? 'red' : 'black'}${c.trump ? ' trump' : ''} ${extra}`.trim() },
    h('span.pc-rank', c.rank), h('span.pc-suit', SUITS[c.suit] || c.suit || ''),
    h('span.pc-big', SUITS[c.suit] || ''));
}

export class CardsView extends View {
  static type = 'cards';

  /** Table positions relative to the viewer, clockwise. */
  positions(n) {
    if (n === 2) return ['south', 'north'];
    if (n === 3) return ['south', 'west', 'east'];
    return ['south', 'west', 'north', 'east'].slice(0, n);
  }

  render(part) {
    const n = part.names.length;
    const pos = this.positions(n);
    const table = h('div.felt');
    for (let k = 0; k < n; k++) {
      const seat = (part.seat + k) % n;
      const where = pos[k];
      const badges = (part.badges?.[seat] || []).map((b) => h('span.chip.tiny', b));
      const box = h(`div.seat.at-${where}`, { class: part.toAct === seat ? 'to-act' : '' },
        h('div.seat-name', { style: { '--pc': this.color(seat) } }, part.names[seat], badges),
        part.taken ? h('div.seat-taken.small.muted', `${part.taken[seat]} pts`) : null);
      if (k !== 0 && part.hands?.[seat]) {
        box.append(h('div.backs.open', part.hands[seat].map((c) => cardEl(c, 'mini'))));
      } else if (k !== 0) {
        const backs = h('div.backs');
        const count = Math.min(part.handSizes?.[seat] || 0, 12);
        for (let i = 0; i < count; i++) backs.append(h('div.pcard.back.mini'));
        box.append(backs);
      }
      table.append(box);
    }
    const trick = h('div.trick');
    for (const play of part.trick || []) {
      const k = (play.seat - part.seat + n) % n;
      trick.append(h(`div.trick-slot.at-${pos[k]}`, cardEl(play.card)));
    }
    if (part.center?.length) trick.append(h('div.center-cards', part.center.map((c) => cardEl(c, 'small'))));
    table.append(trick);
    if (part.lastTrick) {
      table.append(h('div.last-trick.small', h('span.muted', 'Last trick'),
        h('div.row', (part.lastTrick.plays || []).map((p) => cardEl(p.card || p, 'mini'))),
        part.lastTrick.winner != null ? h('span.muted', `to ${part.names[part.lastTrick.winner]}`) : null));
    }
    const hand = h('div.hand');
    (part.hand || []).forEach((c, i) => {
      const el = cardEl(c, c.action != null ? 'playable' : 'dim');
      el.style.setProperty('--i', i);
      el.style.setProperty('--n', part.hand.length);
      hand.append(this.actionable(el, c.action));
    });
    this.el.append(table, hand);
  }
}
