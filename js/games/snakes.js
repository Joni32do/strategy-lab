/* ============================================================
 * Snakes & Ladders — "Lucky Picks" variant.
 * Plain Snakes & Ladders has no decisions at all, so here each
 * turn you roll TWO dice and your strategy picks which one to
 * use. Overshooting 100 bounces you back. First to land exactly
 * on 100 wins.
 * ============================================================ */
(function () {
  'use strict';

  // ladders go up (value > key), snakes go down (value < key) — classic layout
  const JUMPS = {
    1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100,
    16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78,
  };

  function rawDest(pos, die) {
    let t = pos + die;
    if (t > 100) t = 200 - t;          // bounce off the final square
    return t;
  }
  function finalDest(pos, die) {
    const r = rawDest(pos, die);
    return JUMPS[r] !== undefined ? JUMPS[r] : r;
  }
  function rollPair(rng) {
    return [1 + StrategyLab.randInt(rng, 6), 1 + StrategyLab.randInt(rng, 6)];
  }

  /* moves are indices into state.dice */
  const rules = [
    {
      id: 'sniper', name: 'Photo finish', icon: '🎯', kind: 'pick',
      desc: 'If one die lands you exactly on square 100, take it. Game over.',
      pick: (s, cands, seat) =>
        cands.find(m => finalDest(s.pos[seat], s.dice[m]) === 100) ?? null,
    },
    {
      id: 'ladder', name: 'Ladder lover', icon: '🪜', kind: 'pick',
      desc: 'Prefer a die that lands on the foot of a ladder.',
      pick(s, cands, seat) {
        const ups = cands.filter(m => {
          const r = rawDest(s.pos[seat], s.dice[m]);
          return JUMPS[r] !== undefined && JUMPS[r] > r;
        });
        if (!ups.length) return null;
        return ups.reduce((a, b) =>
          finalDest(s.pos[seat], s.dice[a]) >= finalDest(s.pos[seat], s.dice[b]) ? a : b);
      },
    },
    {
      id: 'dodge', name: 'Snake dodger', icon: '🐍', kind: 'avoid',
      desc: 'Veto dice that drop you on a snake head — when you have a choice.',
      avoid(s, m, seat) {
        const r = rawDest(s.pos[seat], s.dice[m]);
        return JUMPS[r] !== undefined && JUMPS[r] < r;
      },
    },
    {
      id: 'no-bounce', name: 'No overshoot', icon: '🧱', kind: 'avoid',
      desc: 'Avoid shooting past square 100 and bouncing backwards.',
      avoid: (s, m, seat) => s.pos[seat] + s.dice[m] > 100,
    },
    {
      id: 'far', name: 'Far sighted', icon: '🔭', kind: 'pick',
      desc: 'Take the die with the best final square — counting snakes, ladders and bounces.',
      pick: (s, cands, seat) => cands.reduce((a, b) =>
        finalDest(s.pos[seat], s.dice[a]) >= finalDest(s.pos[seat], s.dice[b]) ? a : b),
    },
    {
      id: 'big', name: 'Full throttle', icon: '🏎️', kind: 'pick',
      desc: 'Always take the bigger die. Raw speed, no questions.',
      pick: (s, cands) => cands.reduce((a, b) => (s.dice[a] >= s.dice[b] ? a : b)),
    },
    {
      id: 'small', name: 'Baby steps', icon: '🐢', kind: 'pick',
      desc: 'Always take the smaller die. (Bold theory. Test it!)',
      pick: (s, cands) => cands.reduce((a, b) => (s.dice[a] <= s.dice[b] ? a : b)),
    },
  ];

  function cellRowCol(n) {
    const row = Math.floor((n - 1) / 10);            // 0 = bottom row
    const c = (n - 1) % 10;
    const col = row % 2 === 0 ? c : 9 - c;           // boustrophedon
    return { row, col };
  }
  function cellCenter(n) {
    const { row, col } = cellRowCol(n);
    return { x: (col + 0.5) * 10, y: (9 - row + 0.5) * 10 };   // percent coords
  }

  StrategyLab.registerGame({
    id: 'snakes',
    name: 'Snakes & Ladders',
    icon: '🐍',
    level: 'Casual',
    tagline: 'Roll two dice, keep one. How much can strategy beat luck?',
    rules,

    botPresets: [
      {
        id: 'randy', name: 'Randy Rookie', icon: '🐣', stars: 1,
        desc: 'Picks a die at random. Pure chaos.', ruleIds: [],
      },
      {
        id: 'harry', name: 'Hasty Harry', icon: '🏎️', stars: 2,
        desc: 'Always takes the bigger die. Snakes? What snakes?', ruleIds: ['big'],
      },
      {
        id: 'cleo', name: 'Cautious Cleo', icon: '🧐', stars: 3,
        desc: 'Dodges snakes, climbs ladders, then floors it.',
        ruleIds: ['dodge', 'ladder', 'big'],
      },
      {
        id: 'lena', name: 'Lucky Lena', icon: '🍀', stars: 4,
        desc: 'Plays the percentages on every single roll.',
        ruleIds: ['sniper', 'dodge', 'no-bounce', 'ladder', 'far'],
      },
    ],

    maxTurns: 600,

    initialState(rng, firstSeat) {
      return { pos: [0, 0], current: firstSeat, dice: rollPair(rng) };
    },
    currentPlayer: s => s.current,
    legalMoves(s) {
      return s.dice[0] === s.dice[1] ? [0] : [0, 1];
    },
    applyMove(s, move, rng) {
      const n = StrategyLab.clone(s);
      const seat = s.current;
      n.pos[seat] = finalDest(s.pos[seat], s.dice[move]);
      n.current = 1 - seat;
      n.dice = rollPair(rng);
      return n;
    },
    isTerminal: s => s.pos[0] === 100 || s.pos[1] === 100,
    winner: s => (s.pos[0] === 100 ? 0 : s.pos[1] === 100 ? 1 : null),
    timeoutWinner: s => (s.pos[0] === s.pos[1] ? null : (s.pos[0] > s.pos[1] ? 0 : 1)),

    describeMove(s, move, seat) {
      const d = s.dice[move];
      const pos = s.pos[seat];
      const bounced = pos + d > 100;
      const raw = rawDest(pos, d);
      const fin = finalDest(pos, d);
      let txt = `rolls ${s.dice[0]}·${s.dice[1]} and takes the ${d}`;
      txt += bounced ? `, bounces off 100 back to ${raw}` : ` → ${raw}`;
      if (fin > raw) txt += ` — ladder up to ${fin}! 🪜`;
      else if (fin < raw) txt += ` — snake down to ${fin} 🐍`;
      if (fin === 100) txt += ' — finish! 🏁';
      return txt;
    },

    renderState(s, el) {
      let html = '<div class="sl-wrap"><div class="sl-grid">';
      for (let dr = 9; dr >= 0; dr--) {
        for (let col = 0; col < 10; col++) {
          const num = dr % 2 === 0 ? dr * 10 + col + 1 : dr * 10 + (9 - col) + 1;
          const j = JUMPS[num];
          let cls = 'sl-cell';
          let icon = '';
          if (j !== undefined && j > num) { cls += ' ladder'; icon = '<i>🪜</i>'; }
          else if (j !== undefined) { cls += ' snake'; icon = '<i>🐍</i>'; }
          html += `<div class="${cls}"><span>${num}</span>${icon}</div>`;
        }
      }
      html += '</div><svg class="sl-overlay" viewBox="0 0 100 100" preserveAspectRatio="none">';
      for (const [src, dst] of Object.entries(JUMPS)) {
        const a = cellCenter(+src), b = cellCenter(dst);
        const cls = dst > +src ? 'jump-l' : 'jump-s';
        html += `<line class="${cls}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
      }
      html += '</svg>';
      for (const seat of [0, 1]) {
        if (s.pos[seat] > 0) {
          const { x, y } = cellCenter(s.pos[seat]);
          html += `<div class="sl-tok t${seat}" style="left:${x}%;top:${y}%"></div>`;
        }
      }
      html += '</div>';
      const where = p => (p === 0 ? 'start' : p === 100 ? '🏁 100' : 'square ' + p);
      html += `<div class="board-status"><span class="lab0">●</span> You: ${where(s.pos[0])}` +
        ` &nbsp;·&nbsp; <span class="lab1">●</span> Bot: ${where(s.pos[1])}` +
        ` &nbsp;·&nbsp; 🎲 ${s.dice[0]}·${s.dice[1]}</div>`;
      el.innerHTML = html;
    },

    insight({ userWins, botWins, n }) {
      const diff = userWins - botWins;
      if (Math.abs(diff) <= 12) {
        return 'Dead even. Once both sides pick their dice halfway sensibly, the rest is pure ' +
          'dice — there is no fork or checkmate hiding in Snakes & Ladders, so two decent ' +
          'policies converge to a coin flip. Recognizing where the skill ceiling of a game ' +
          'sits is a strategy insight too. Compare this with Tic-Tac-Toe!';
      }
      if (diff > 12) {
        return 'A real edge in a luck-heavy race: ' + userWins + ' vs ' + botWins + '. Small ' +
          'advantages per roll — taking ladders, dodging snakes, never overshooting — compound ' +
          'over 100 games. That is exactly how casinos make money.';
      }
      return null;
    },
  });
})();
