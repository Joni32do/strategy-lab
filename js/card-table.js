/* ============================================================
 * Strategy Lab - card-table renderer for Skat + Doppelkopf.
 *
 * env-play.js (renderSpiel) hands us the server payload `d` when
 * it carries `d.cardView` (the frozen contract below) and asks us
 * to draw a felt table INSTEAD of the plain <pre> obs + legal-move
 * buttons. Everything else on the page (header, rule toggles,
 * controls, move log, returns banner) stays owned by env-play.
 *
 * We fully re-render from `d.cardView` on every call (idempotent),
 * exactly like env-play re-renders after each act. A completed
 * trick lingers ~1s (winner highlighted) before the live state
 * sweeps in -- driven by a per-sid snapshot + a render token so a
 * newer render cancels a pending linger timer.
 *
 * Source is ASCII; suit glyphs are unicode escapes so the file
 * stays ASCII while the DOM shows real club/spade/heart/diamond.
 *
 * cardView contract (server emits exactly this):
 *   kind 'doppelkopf'|'skat', phase 'play'|'bid'|'discard',
 *   players 4|3, humanSeat, toAct int|null, terminal,
 *   seatNames [str] (human is 'You'),
 *   hand [ {a, rank, suit 0..3, trump, points, legal} ] (a null if unplayable),
 *   handSizes [int], trick {leader, plays:[{seat,rank,suit}]},
 *   lastTrick {winner, points, plays[]} | null,
 *   pointsTaken [int]|null, badges [[str,...]], actions [{a,s}],
 *   status str, result null|object.
 * Suits: 0=Clubs 1=Spades 2=Hearts 3=Diamonds; hearts+diamonds red.
 * ============================================================ */
(function () {
  'use strict';

  var g = typeof window !== 'undefined' ? window : global;
  var hasDoc = typeof document !== 'undefined';

  var LINGER_MS = 1000;
  /* club, spade, heart, diamond -- unicode escapes keep the file ASCII */
  var GLYPHS = ['\u2663', '\u2660', '\u2665', '\u2666'];
  var MAX_BACKS = 12;

  /* --------------------------- pure helpers ---------------------------- */

  function cardGlyph(suit) { return GLYPHS[suit] || '?'; }

  /* Hearts (2) and diamonds (3) get the red treatment. */
  function isRed(suit) { return suit === 2 || suit === 3; }

  /* Map each seat index to a table position. The human always sits
   * 'south' (bottom); the others fan clockwise from the human's left.
   * 4 players -> south/west/north/east; 3 players -> south + two
   * opponents top-left (west) and top-right (east). */
  function seatLayout(players, humanSeat) {
    var order = players === 3
      ? ['south', 'west', 'east']
      : ['south', 'west', 'north', 'east'];
    var map = {};
    for (var i = 0; i < players; i++) {
      var seat = (((humanSeat + i) % players) + players) % players;
      map[seat] = order[i];
    }
    return map;
  }

  /* True when the game just completed a trick: the previous view had
   * cards on the table, the next view's live trick is empty, and a
   * fresh lastTrick is present to linger on. */
  function trickChanged(prevView, nextView) {
    if (!prevView || !nextView) return false;
    var prevN = prevView.trick && prevView.trick.plays ? prevView.trick.plays.length : 0;
    var nextN = nextView.trick && nextView.trick.plays ? nextView.trick.plays.length : 0;
    return prevN > 0 && nextN === 0 && !!nextView.lastTrick;
  }

  /* ----------------------------- rendering ----------------------------- */

  var renderToken = 0;      // bump to orphan a pending linger timer
  var prevBySid = {};       // last-seen cardView per session id

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* Build one card face. `tag` is 'button' for the hand (clickable),
   * 'div' for the trick. opts: {trump, points, disabled, winner, extra}. */
  function makeCard(tag, rank, suit, opts) {
    opts = opts || {};
    var cls = 'ct-card'
      + (isRed(suit) ? ' red' : '')
      + (opts.trump ? ' trump' : '')
      + (opts.disabled ? ' disabled' : '')
      + (opts.winner ? ' ct-win' : '')
      + (opts.extra ? ' ' + opts.extra : '');
    var c = el(tag, cls);
    var corner = el('span', 'ct-corner');
    corner.appendChild(el('span', 'ct-rank', rank));
    corner.appendChild(el('span', 'ct-csuit', cardGlyph(suit)));
    c.appendChild(corner);
    c.appendChild(el('span', 'ct-pip', cardGlyph(suit)));
    if (opts.points) c.appendChild(el('span', 'ct-pts', String(opts.points)));
    return c;
  }

  function badgeChips(list) {
    var wrap = el('span', 'ct-badges');
    (list || []).forEach(function (b) { wrap.appendChild(el('span', 'ct-badge', b)); });
    return wrap;
  }

  /* Seats around the felt (card backs + name + badges). The human's
   * seat shows its label only -- the real hand renders below the table. */
  function buildSeats(view, layout) {
    var frag = document.createDocumentFragment();
    for (var seat = 0; seat < view.players; seat++) {
      var pos = layout[seat];
      var toAct = !view.terminal && view.toAct === seat;
      var s = el('div', 'ct-seat ct-' + pos + (toAct ? ' ct-toact' : ''));
      var label = el('div', 'ct-seat-label');
      label.appendChild(el('span', 'ct-seat-name', view.seatNames[seat]));
      label.appendChild(badgeChips(view.badges && view.badges[seat]));
      s.appendChild(label);
      if (seat !== view.humanSeat) {
        var backs = el('div', 'ct-backs');
        var n = Math.min(view.handSizes[seat] || 0, MAX_BACKS);
        for (var i = 0; i < n; i++) backs.appendChild(el('div', 'ct-back'));
        s.appendChild(backs);
      }
      frag.appendChild(s);
    }
    return frag;
  }

  /* Center trick area: one placed card per play, positioned at the
   * playing seat's table slot. `winnerSeat` (or null) highlights. */
  function buildTrick(view, layout, plays, winnerSeat) {
    var trick = el('div', 'ct-trick');
    (plays || []).forEach(function (p) {
      var slot = el('div', 'ct-slot ct-slot-' + layout[p.seat]);
      slot.appendChild(makeCard('div', p.rank, p.suit, { winner: winnerSeat === p.seat }));
      trick.appendChild(slot);
    });
    return trick;
  }

  function buildScore(view) {
    if (!view.pointsTaken) return null;
    var strip = el('div', 'ct-score');
    for (var seat = 0; seat < view.players; seat++) {
      var cell = el('div', 'ct-score-cell' + (seat === view.humanSeat ? ' ct-you' : ''));
      cell.appendChild(el('span', 'ct-score-name', view.seatNames[seat]));
      cell.appendChild(el('span', 'ct-score-pts', String(view.pointsTaken[seat])));
      strip.appendChild(cell);
    }
    return strip;
  }

  /* Non-card actions (skat bidding, discard confirmation, ...). */
  function buildActions(view, act) {
    if (!view.actions || !view.actions.length) return null;
    var strip = el('div', 'ct-actions');
    view.actions.forEach(function (a) {
      var b = el('button', 'ct-act-btn', a.s);
      b.addEventListener('click', function () { act({ action: a.a }); });
      strip.appendChild(b);
    });
    return strip;
  }

  /* The human hand as clickable card buttons. Legal + playable cards
   * fire act({action}); everything else is disabled/dimmed. */
  function buildHand(view, act) {
    var hand = el('div', 'ct-hand');
    (view.hand || []).forEach(function (card) {
      var playable = card.legal === true && card.a != null;
      var node = makeCard('button', card.rank, card.suit, {
        trump: card.trump,
        points: card.points,
        disabled: !playable,
      });
      if (playable) {
        node.addEventListener('click', function () { act({ action: card.a }); });
      } else {
        node.disabled = true;
      }
      hand.appendChild(node);
    });
    return hand;
  }

  function retRow(view) {
    var res = view.result || {};
    var returns = res.returns || [];
    var row = el('div', 'ct-ret');
    for (var seat = 0; seat < view.players; seat++) {
      var cell = el('div', 'ct-ret-cell' + (seat === view.humanSeat ? ' ct-you' : ''));
      cell.appendChild(el('span', 'ct-ret-name', view.seatNames[seat]));
      var v = returns[seat];
      cell.appendChild(el('span', 'ct-ret-val', (v > 0 ? '+' : '') + (v == null ? '0' : v)));
      row.appendChild(cell);
    }
    return row;
  }

  /* Terminal breakdown. Doppelkopf gets the Re/Kontra 121-target split,
   * game value and specials; skat just the per-seat returns. */
  function buildResult(view) {
    if (!view.terminal || !view.result) return null;
    var res = view.result;
    var banner = el('div', 'ct-result');
    banner.appendChild(el('div', 'ct-result-head', 'Game over'));
    if (view.kind === 'doppelkopf') {
      var pts = el('div', 'ct-result-pts');
      pts.appendChild(el('span', 'ct-pill',
        'Re ' + (res.re_points == null ? '?' : res.re_points) + ' / 121'));
      pts.appendChild(el('span', 'ct-pill',
        'Kontra ' + (res.kontra_points == null ? '?' : res.kontra_points)));
      if (res.value != null) {
        pts.appendChild(el('span', 'ct-pill ct-pill-val',
          'value ' + (res.value >= 0 ? '+' : '') + res.value));
      }
      banner.appendChild(pts);
      if (res.specials && res.specials.length) {
        var sp = el('div', 'ct-result-specials');
        res.specials.forEach(function (s) {
          var label = Array.isArray(s) ? s[0] : s;
          sp.appendChild(el('span', 'ct-badge', String(label)));
        });
        banner.appendChild(sp);
      }
    }
    banner.appendChild(retRow(view));
    return banner;
  }

  /* One full paint. `plays`/`winnerSeat` let the linger override the
   * live trick with the just-completed one. */
  function paint(hostEl, d, act, plays, winnerSeat) {
    var view = d.cardView;
    var layout = seatLayout(view.players, view.humanSeat);
    hostEl.className = 'ct-host ct-' + view.kind;
    hostEl.innerHTML = '';

    var table = el('div', 'ct-table');
    table.appendChild(buildSeats(view, layout));
    table.appendChild(buildTrick(view, layout, plays, winnerSeat));
    hostEl.appendChild(table);

    var result = buildResult(view);
    if (result) hostEl.appendChild(result);

    var score = buildScore(view);
    if (score) hostEl.appendChild(score);

    hostEl.appendChild(el('div', 'ct-status', view.status || ''));

    var actions = buildActions(view, act);
    if (actions) hostEl.appendChild(actions);

    hostEl.appendChild(buildHand(view, act));
  }

  /* Public entry: called by env-play after every act. */
  function render(hostEl, d, opts) {
    var view = d && d.cardView;
    if (!hostEl || !view) return;
    var act = (opts && opts.act) || function () {};
    renderToken++;
    var my = renderToken;
    var sid = d.sid;
    var prev = prevBySid[sid];
    if (sid != null) prevBySid[sid] = view;

    if (!hasDoc) return;   // node/test context: snapshot only, no DOM

    if (trickChanged(prev, view)) {
      // Linger on the completed trick (winner lit) before the live state.
      var lt = view.lastTrick;
      paint(hostEl, d, act, lt.plays, lt.winner);
      setTimeout(function () {
        if (my !== renderToken) return;   // a newer render superseded us
        paint(hostEl, d, act, view.trick && view.trick.plays, null);
      }, LINGER_MS);
    } else {
      paint(hostEl, d, act, view.trick && view.trick.plays, null);
    }
  }

  var CardTable = {
    render: render,
    _pure: {
      cardGlyph: cardGlyph,
      isRed: isRed,
      seatLayout: seatLayout,
      trickChanged: trickChanged,
    },
  };

  g.CardTable = CardTable;
  if (typeof module !== 'undefined' && module.exports) module.exports = CardTable;
})();
