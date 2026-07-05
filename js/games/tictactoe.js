/* ============================================================
 * Tic-Tac-Toe — the "hello world" of solved games.
 * With the right card order (win → block → fork → smother →
 * center → mirror corner → corner → edge) play is perfect and
 * every game ends in a draw.
 * ============================================================ */
(function () {
  'use strict';

  const LINES = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6],
  ];
  const CORNERS = [0, 2, 6, 8];
  const EDGES = [1, 3, 5, 7];
  const OPPOSITE = { 0: 8, 2: 6, 6: 2, 8: 0 };
  const CELL_NAMES = ['top-left', 'top', 'top-right', 'left', 'center',
    'right', 'bottom-left', 'bottom', 'bottom-right'];

  function findWinLine(board) {
    for (const line of LINES) {
      const [a, b, c] = line;
      if (board[a] !== null && board[a] === board[b] && board[b] === board[c]) return line;
    }
    return null;
  }
  function winnerOf(board) {
    const line = findWinLine(board);
    return line ? board[line[0]] : null;
  }
  function winsNow(board, cell, seat) {
    board[cell] = seat;
    const w = winnerOf(board) === seat;
    board[cell] = null;
    return w;
  }
  /* squares that would complete a two-in-a-row for `seat` */
  function threatSquares(board, seat) {
    const res = [];
    for (const line of LINES) {
      let mine = 0, empty = -1, blocked = false;
      for (const c of line) {
        if (board[c] === seat) mine++;
        else if (board[c] === null) empty = c;
        else blocked = true;
      }
      if (!blocked && mine === 2 && empty !== -1) res.push(empty);
    }
    return res;
  }
  function makesFork(board, cell, seat) {
    board[cell] = seat;
    const f = threatSquares(board, seat).length >= 2;
    board[cell] = null;
    return f;
  }

  const rules = [
    {
      id: 'win', name: 'Finish it', icon: '🏆', kind: 'pick',
      desc: 'If a move wins the game right now, play it.',
      pick: (s, cands, seat) => cands.find(c => winsNow(s.board, c, seat)) ?? null,
    },
    {
      id: 'block', name: 'Block the win', icon: '🛡️', kind: 'pick',
      desc: 'If the opponent could win next turn, take that square first.',
      pick: (s, cands, seat) => cands.find(c => winsNow(s.board, c, 1 - seat)) ?? null,
    },
    {
      id: 'fork', name: 'Build a fork', icon: '🔱', kind: 'pick',
      desc: 'Create two winning threats at once — only one can be blocked.',
      pick: (s, cands, seat) => cands.find(c => makesFork(s.board, c, seat)) ?? null,
    },
    {
      id: 'block-fork', name: 'Smother forks', icon: '🚧', kind: 'pick',
      desc: 'Stop the opponent from setting up a double threat.',
      pick(s, cands, seat) {
        const opp = 1 - seat, b = s.board;
        const forks = cands.filter(c => makesFork(b, c, opp));
        if (forks.length === 0) return null;
        if (forks.length === 1) return forks[0];
        // Several fork squares: occupying one leaves the other open, so
        // instead force a defense — make a two-in-a-row whose completion
        // square is not itself a fork square for the opponent.
        for (const c of cands) {
          b[c] = seat;
          const completions = threatSquares(b, seat);
          const safe = completions.length > 0 &&
            completions.every(e => !makesFork(b, e, opp));
          b[c] = null;
          if (safe) return c;
        }
        return forks[0];
      },
    },
    {
      id: 'center', name: 'Take the center', icon: '🎯', kind: 'pick',
      desc: 'The middle square sits on four lines — grab it.',
      pick: (s, cands) => (cands.includes(4) ? 4 : null),
    },
    {
      id: 'opp-corner', name: 'Mirror corner', icon: '🪞', kind: 'pick',
      desc: 'If the opponent holds a corner, take the one diagonally opposite.',
      pick(s, cands, seat) {
        for (const c of CORNERS) {
          if (s.board[c] === 1 - seat && cands.includes(OPPOSITE[c])) return OPPOSITE[c];
        }
        return null;
      },
    },
    {
      id: 'corner', name: 'Grab a corner', icon: '📐', kind: 'pick',
      desc: 'Corners each sit on three lines — strong real estate.',
      pick(s, cands, seat, rng) {
        const cs = cands.filter(c => CORNERS.includes(c));
        return cs.length ? StrategyLab.pickRandom(rng, cs) : null;
      },
    },
    {
      id: 'edge', name: 'Take an edge', icon: '➖', kind: 'pick',
      desc: 'Settle for a side square.',
      pick(s, cands, seat, rng) {
        const es = cands.filter(c => EDGES.includes(c));
        return es.length ? StrategyLab.pickRandom(rng, es) : null;
      },
    },
  ];

  StrategyLab.registerGame({
    id: 'tictactoe',
    name: 'Tic-Tac-Toe',
    icon: '⭕',
    level: 'Starter',
    tagline: 'The classic 3×3 duel. Mathematically solved — can you re-solve it?',
    rules,

    botPresets: [
      {
        id: 'randy', name: 'Randy Rookie', icon: '🐣', stars: 1,
        desc: 'Plays completely random squares.', ruleIds: [],
      },
      {
        id: 'gus', name: 'Greedy Gus', icon: '😋', stars: 2,
        desc: 'Takes a win when he sees one. Otherwise? Vibes.', ruleIds: ['win'],
      },
      {
        id: 'carla', name: 'Careful Carla', icon: '🧐', stars: 3,
        desc: 'Wins when possible and blocks your wins — but has no plan.',
        ruleIds: ['win', 'block'],
      },
      {
        id: 'minnie', name: 'Minnie Max', icon: '🤖', stars: 4,
        desc: 'Textbook perfect play. She cannot be beaten — only drawn.',
        ruleIds: ['win', 'block', 'fork', 'block-fork', 'center', 'opp-corner', 'corner', 'edge'],
      },
    ],

    maxTurns: 9,

    initialState(rng, firstSeat) {
      return {
        board: Array(9).fill(null),
        current: firstSeat,
        marks: firstSeat === 0 ? ['X', 'O'] : ['O', 'X'],   // whoever starts plays X
      };
    },
    currentPlayer: s => s.current,
    legalMoves(s) {
      const m = [];
      for (let i = 0; i < 9; i++) if (s.board[i] === null) m.push(i);
      return m;
    },
    applyMove(s, move) {
      const n = StrategyLab.clone(s);
      if (move !== null) n.board[move] = s.current;
      n.current = 1 - s.current;
      return n;
    },
    isTerminal: s => winnerOf(s.board) !== null || s.board.every(c => c !== null),
    winner: s => winnerOf(s.board),

    describeMove(s, move, seat) {
      return `places ${s.marks[seat]} in the ${CELL_NAMES[move]} square`;
    },

    renderState(s, el) {
      const winLine = findWinLine(s.board);
      const grid = document.createElement('div');
      grid.className = 'ttt-board';
      for (let i = 0; i < 9; i++) {
        const cell = document.createElement('div');
        cell.className = 'ttt-cell';
        const v = s.board[i];
        if (v !== null) {
          cell.textContent = s.marks[v];
          cell.classList.add('seat' + v);
        }
        if (winLine && winLine.includes(i)) cell.classList.add('win');
        grid.appendChild(cell);
      }
      el.innerHTML = '';
      el.appendChild(grid);
    },

    insight({ userWins, botWins, draws, n, botPresetId }) {
      if (draws === n) {
        return 'All ' + n + ' games were draws — that is Tic-Tac-Toe, solved. 🎓 With perfect ' +
          'play on both sides the game always ends in a draw: you have found the deterministic ' +
          'optimal policy. No strategy can do better; only worse.';
      }
      if (botPresetId === 'minnie' && userWins === 0 && botWins > 0) {
        return 'Minnie Max never loses — every game you did not draw, you lost. The perfect ' +
          'order is known since 1972: Finish it → Block → Fork → Smother forks → Center → ' +
          'Mirror corner → Corner → Edge. How close is your stack?';
      }
      if (botPresetId !== 'minnie' && userWins > n * 0.8) {
        return 'You are crushing this opponent. The real test is Minnie Max: against perfect ' +
          'play the very best you can achieve is 100 draws.';
      }
      return null;
    },
  });
})();
