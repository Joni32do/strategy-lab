/* Headless tests for the card-table pure helpers: node test/card-table.js
   DOM-free; shims global.window before requiring the module (the module
   is a node-safe IIFE that also module.exports its public surface). */
'use strict';
global.window = global;
const CT = require('../js/card-table.js');

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? 'PASS' : 'FAIL') + '  ' + name + (extra ? '   ' + extra : ''));
  if (!cond) fails++;
}

const P = CT._pure;

/* ---- cardGlyph / isRed ---- */
/* Suits 0=Clubs 1=Spades 2=Hearts 3=Diamonds; the glyph escapes must
   decode to the real club/spade/heart/diamond characters. */
check('cardGlyph maps clubs to the club glyph', P.cardGlyph(0) === '\u2663', P.cardGlyph(0));
check('cardGlyph maps spades to the spade glyph', P.cardGlyph(1) === '\u2660', P.cardGlyph(1));
check('cardGlyph maps hearts to the heart glyph', P.cardGlyph(2) === '\u2665', P.cardGlyph(2));
check('cardGlyph maps diamonds to the diamond glyph', P.cardGlyph(3) === '\u2666', P.cardGlyph(3));

check('isRed: clubs+spades are black', P.isRed(0) === false && P.isRed(1) === false);
check('isRed: hearts+diamonds are red', P.isRed(2) === true && P.isRed(3) === true);

/* ---- seatLayout ---- */
const l4 = P.seatLayout(4, 0);
check('seatLayout(4,0): human seat 0 sits south', l4[0] === 'south', JSON.stringify(l4));
check('seatLayout(4,0): three others fill west/north/east',
  l4[1] === 'west' && l4[2] === 'north' && l4[3] === 'east', JSON.stringify(l4));

const l4b = P.seatLayout(4, 2);
check('seatLayout(4,2): human seat 2 sits south', l4b[2] === 'south', JSON.stringify(l4b));
check('seatLayout(4,2): every seat gets a distinct position',
  new Set(Object.values(l4b)).size === 4, JSON.stringify(l4b));

const l3 = P.seatLayout(3, 0);
check('seatLayout(3,0): human seat 0 sits south', l3[0] === 'south', JSON.stringify(l3));
check('seatLayout(3,0): two opponents on west/east (top corners)',
  l3[1] === 'west' && l3[2] === 'east' && Object.keys(l3).length === 3, JSON.stringify(l3));

/* ---- trickChanged ---- */
const withPlays = { trick: { plays: [{ seat: 0, rank: 'A', suit: 0 }] }, lastTrick: null };
const cleared = { trick: { plays: [] }, lastTrick: { winner: 1, points: 11, plays: [] } };
const midTrick = { trick: { plays: [{ seat: 2, rank: 'K', suit: 1 }] }, lastTrick: null };

check('trickChanged: full trick -> cleared trick with new lastTrick is true',
  P.trickChanged(withPlays, cleared) === true);
check('trickChanged: still mid-trick is false',
  P.trickChanged(withPlays, midTrick) === false);
check('trickChanged: cleared but no lastTrick is false',
  P.trickChanged(withPlays, { trick: { plays: [] }, lastTrick: null }) === false);
check('trickChanged: missing prev/next is false',
  P.trickChanged(null, cleared) === false && P.trickChanged(withPlays, null) === false);

console.log(fails ? ('\n' + fails + ' check(s) FAILED') : '\nAll card-table checks passed.');
process.exit(fails ? 1 : 0);
