/* ============================================================
 * Mensch ärgere dich nicht — 2-player version.
 * 40-field ring, 4 tokens each, enter on a 6 (and roll again
 * after any 6), capture by landing on an enemy token, exact
 * rolls to enter the 4-field home row. First with all 4 tokens
 * home wins.
 *
 * Token positions: -1 = base, 0..39 = absolute track square,
 * 100+h = home cell h (0..3).
 * ============================================================ */
(function () {
  'use strict';

  const N = 40, HOME = 100, BASE = -1;
  const startOf = seat => seat * 20;
  /* how far around the ring a token has travelled, from its owner's view */
  const prog = (seat, abs) => (abs - startOf(seat) + N) % N;

  function destOf(move, seat) {
    if (move.type === 'enter') return startOf(seat);
    if (move.type === 'home') return HOME + move.h;
    return move.dest;
  }
  function tokenValue(seat, p) {           // for timeout tie-breaks
    if (p === BASE) return 0;
    if (p >= HOME) return N + 1 + (p - HOME);
    return prog(seat, p) + 1;
  }

  const rules = [
    {
      id: 'enter', name: 'Fresh legs', icon: '🚪', kind: 'pick',
      desc: 'Rolled a 6? Bring a new token onto the board.',
      pick: (s, cands) => cands.find(m => m.type === 'enter') ?? null,
    },
    {
      id: 'hunt', name: 'Headhunter', icon: '⚔️', kind: 'pick',
      desc: 'If you can capture an enemy token, do it — the furthest one first.',
      pick(s, cands, seat) {
        const opp = s.tokens[1 - seat];
        const caps = cands.filter(m => {
          const d = destOf(m, seat);
          return d < HOME && opp.includes(d);
        });
        if (!caps.length) return null;
        return caps.reduce((a, b) =>
          prog(1 - seat, destOf(a, seat)) >= prog(1 - seat, destOf(b, seat)) ? a : b);
      },
    },
    {
      id: 'home', name: 'Safe harbor', icon: '🏠', kind: 'pick',
      desc: 'Move a token into your home row whenever you can.',
      pick: (s, cands) => cands.find(m => m.type === 'home') ?? null,
    },
    {
      id: 'dodge', name: 'Out of reach', icon: '🛡️', kind: 'avoid',
      desc: 'Avoid stopping 1–6 squares in front of an enemy token.',
      avoid(s, m, seat) {
        const d = destOf(m, seat);
        if (d >= HOME) return false;
        return s.tokens[1 - seat].some(p => {
          if (p < 0 || p >= HOME) return false;
          const gap = (d - p + N) % N;
          return gap >= 1 && gap <= 6;
        });
      },
    },
    {
      id: 'front', name: 'Front runner', icon: '🏃', kind: 'pick',
      desc: 'Push your most advanced token onward.',
      pick(s, cands, seat) {
        const moves = cands.filter(m => m.type !== 'enter');
        if (!moves.length) return null;
        return moves.reduce((a, b) =>
          prog(seat, s.tokens[seat][a.token]) >= prog(seat, s.tokens[seat][b.token]) ? a : b);
      },
    },
    {
      id: 'rear', name: 'Rear guard', icon: '🐢', kind: 'pick',
      desc: 'Push your least advanced board token — keep the pack together.',
      pick(s, cands, seat) {
        const moves = cands.filter(m => m.type !== 'enter');
        if (!moves.length) return null;
        return moves.reduce((a, b) =>
          prog(seat, s.tokens[seat][a.token]) <= prog(seat, s.tokens[seat][b.token]) ? a : b);
      },
    },
  ];

  StrategyLab.registerGame({
    id: 'maedn',
    name: 'Mensch ärgere dich nicht',
    icon: '😤',
    level: 'Advanced',
    tagline: 'Race four tokens home — and kick your opponent back to base.',
    rules,

    botPresets: [
      {
        id: 'randy', name: 'Randy Rookie', icon: '🐣', stars: 1,
        desc: 'Moves whatever, whenever. Bless him.', ruleIds: [],
      },
      {
        id: 'sven', name: 'Sprint Sven', icon: '🏃', stars: 2,
        desc: 'Tunnel vision: always pushes his lead token.', ruleIds: ['front'],
      },
      {
        id: 'hugo', name: 'Hunter Hugo', icon: '⚔️', stars: 3,
        desc: 'Lives for the capture, keeps fresh tokens coming.',
        ruleIds: ['hunt', 'enter', 'front'],
      },
      {
        id: 'greta', name: 'Grandmaster Greta', icon: '👵', stars: 4,
        desc: 'Decades of family-table dominance distilled into five rules.',
        ruleIds: ['home', 'hunt', 'enter', 'dodge', 'front'],
      },
    ],

    maxTurns: 1500,

    initialState(rng, firstSeat) {
      return {
        tokens: [[BASE, BASE, BASE, BASE], [BASE, BASE, BASE, BASE]],
        current: firstSeat,
        dice: 1 + StrategyLab.randInt(rng, 6),
      };
    },
    currentPlayer: s => s.current,

    legalMoves(s) {
      const seat = s.current, d = s.dice, my = s.tokens[seat];
      const moves = [];
      if (d === 6) {
        const baseIdx = my.indexOf(BASE);
        if (baseIdx !== -1 && !my.includes(startOf(seat))) {
          moves.push({ type: 'enter', token: baseIdx });
        }
      }
      for (let i = 0; i < 4; i++) {
        const p = my[i];
        if (p === BASE || p >= HOME) continue;
        const np = prog(seat, p) + d;
        if (np <= N - 1) {
          const dest = (startOf(seat) + np) % N;
          if (!my.includes(dest)) moves.push({ type: 'move', token: i, dest });
        } else if (np <= N + 3) {
          const h = np - N;
          if (!my.includes(HOME + h)) moves.push({ type: 'home', token: i, h });
        }
      }
      return moves;
    },

    applyMove(s, move, rng) {
      const n = StrategyLab.clone(s);
      const seat = s.current;
      if (move) {
        const my = n.tokens[seat], opp = n.tokens[1 - seat];
        const dest = destOf(move, seat);
        if (dest < HOME) {
          const oi = opp.indexOf(dest);
          if (oi !== -1) opp[oi] = BASE;          // capture!
        }
        my[move.token] = dest;
      }
      const extraTurn = s.dice === 6 && move;     // a 6 grants another roll
      n.current = extraTurn ? seat : 1 - seat;
      n.dice = 1 + StrategyLab.randInt(rng, 6);
      return n;
    },

    isTerminal: s =>
      s.tokens[0].every(p => p >= HOME) || s.tokens[1].every(p => p >= HOME),
    winner(s) {
      if (s.tokens[0].every(p => p >= HOME)) return 0;
      if (s.tokens[1].every(p => p >= HOME)) return 1;
      return null;
    },
    timeoutWinner(s) {
      const score = seat => s.tokens[seat].reduce((t, p) => t + tokenValue(seat, p), 0);
      const a = score(0), b = score(1);
      return a === b ? null : a > b ? 0 : 1;
    },

    describeMove(s, move, seat) {
      const d = s.dice;
      const again = d === 6 && move ? ' — and rolls again' : '';
      if (!move) return `rolls ${d} — no legal move, turn passes`;
      if (move.type === 'enter') {
        const captures = s.tokens[1 - seat].includes(startOf(seat));
        return `rolls 6 — a fresh token enters the board` +
          (captures ? ' and kicks an enemy token back to base! 💥' : '') + again;
      }
      if (move.type === 'home') return `rolls ${d} — token ${move.token + 1} reaches home 🏠${again}`;
      const captures = s.tokens[1 - seat].includes(move.dest);
      return `rolls ${d} — moves token ${move.token + 1}` +
        (captures ? ' and kicks an enemy token back to base! 💥' : '') + again;
    },

    renderState(s, el) {
      const W = 268, c = 134, R = 100;
      const ang = i => (i / N) * 2 * Math.PI - Math.PI / 2;
      const xy = (a, r) => [(c + r * Math.cos(a)).toFixed(1), (c + r * Math.sin(a)).toFixed(1)];
      const BASE_OFF = [[-7, -7], [7, -7], [-7, 7], [7, 7]];

      let svg = `<svg class="maedn" viewBox="0 0 ${W} ${W}">`;
      for (let i = 0; i < N; i++) {
        const [x, y] = xy(ang(i), R);
        const cls = i === 0 ? 'cell start0' : i === 20 ? 'cell start1' : 'cell';
        svg += `<circle class="${cls}" cx="${x}" cy="${y}" r="7"/>`;
      }
      const slotXY = (seat, p, off) => {
        if (p >= HOME) return xy(ang(startOf(seat)), R - 17 - (p - HOME) * 16);
        if (p === BASE) {
          const [bx, by] = xy(ang((startOf(seat) + N - 3) % N), R + 16);
          return [(+bx + BASE_OFF[off][0]).toFixed(1), (+by + BASE_OFF[off][1]).toFixed(1)];
        }
        return xy(ang(p), R);
      };
      for (const seat of [0, 1]) {
        for (let h = 0; h < 4; h++) {
          const [x, y] = slotXY(seat, HOME + h, 0);
          svg += `<circle class="cell home${seat}" cx="${x}" cy="${y}" r="6"/>`;
        }
        for (let k = 0; k < 4; k++) {
          const [x, y] = slotXY(seat, BASE, k);
          svg += `<circle class="cell base${seat}" cx="${x}" cy="${y}" r="5"/>`;
        }
      }
      for (const seat of [0, 1]) {
        let baseSlot = 0;
        s.tokens[seat].forEach(p => {
          const [x, y] = slotXY(seat, p, p === BASE ? baseSlot++ : 0);
          svg += `<circle class="tok tok${seat}" cx="${x}" cy="${y}" r="5"/>`;
        });
      }
      svg += `<circle class="tok tok${s.current}" cx="${c - 22}" cy="${c - 1}" r="5"/>`;
      svg += `<text class="dice" x="${c + 8}" y="${c + 5}">🎲 ${s.dice}</text>`;
      svg += '</svg>';

      const summary = seat => {
        const t = s.tokens[seat];
        const home = t.filter(p => p >= HOME).length;
        const base = t.filter(p => p === BASE).length;
        return `${home} home · ${4 - home - base} on track · ${base} in base`;
      };
      el.innerHTML = svg +
        `<div class="board-status"><span class="lab0">●</span> You: ${summary(0)}` +
        ` &nbsp;·&nbsp; <span class="lab1">●</span> Bot: ${summary(1)}</div>`;
    },

    insight({ userWins, botWins, n, userRuleIds }) {
      if (!userRuleIds.includes('enter') && userWins < botWins) {
        return 'Tokens stuck in the base score nothing — without a "Fresh legs" card your ' +
          'strategy only brings tokens out by accident. Most strong stacks start with entering, ' +
          'capturing, and getting home safely; the interesting part is the order.';
      }
      if (userWins > botWins && userWins >= n * 0.6) {
        return 'Strong showing! Unlike Tic-Tac-Toe there is no known perfect policy here — ' +
          'dice keep the outcome noisy, but good priorities (capture, enter, stay out of reach) ' +
          'shift the odds far more than in Snakes & Ladders. This game sits between luck and skill.';
      }
      return null;
    },
  });
})();
