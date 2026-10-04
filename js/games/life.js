/* ============================================================
 * The Game of Life (Milton Bradley) -- 2-player version.
 *
 * A linear life track from Start to Retirement. A spinner (1..10)
 * moves you along; passing a payday marker collects your salary.
 * Net worth (cash, with the retirement payout folded in) decides
 * the winner. The two players do not interact -- each is racing
 * their own bank balance -- so every choice is a pure risk/reward
 * lever the rule cards can pull.
 *
 * DECISION spaces (return multiple legalMoves):
 *   fork    college vs career (tuition now for higher salaries)
 *   career  pick a salary (steady vs high, low-tier vs high-tier)
 *   insure  buy full insurance (costs now, waives later hazards)
 *   gamble  stock market: risk cash on a spin, or walk past
 *   retire  Countryside Acres (safe) vs Millionaire Estates (spin)
 * Ordinary "spin" spaces return a single forced advance move.
 *
 * All money is in $1000 units ("k"). Positions run 0..FINISH.
 * ============================================================ */
(function () {
  'use strict';

  const ri = StrategyLab.randInt;
  const spin10 = rng => 1 + ri(rng, 10);            // the spinner: 1..10

  const FINISH = 60;
  const PAYDAY = 8;                                  // salary at 8,16,..,56
  const INS_AT = 12;                                // insurance milestone
  const GAMBLE_AT = [24, 40];                        // stock-market milestones
  const HAZARD_AT = [20, 44];                        // automatic accident checks
  const MARRY_AT = 30, BABY_AT = 50;                 // small automatic collects

  const TUITION = 40;                                // college student loan
  const INSURANCE_COST = 15;
  const HAZARD_COST = 40;                             // paid if unlucky + uninsured
  const GAMBLE_WIN = 40, GAMBLE_LOSE = 30;           // stock-market payout / loss
  const COUNTRY = 100;                               // Countryside Acres payout
  const ESTATE_PER = 24;                             // Millionaire Estates: spin*this
  const MARRY_GIFT = 20, BABY_GIFT = 12;

  /* careers: pay is per-payday base ($k); var is the +/- swing. */
  const BASE_CAREERS = [
    { id: 'server', name: 'Server', icon: '🍔', pay: 12, var: 0 },
    { id: 'sales', name: 'Salesperson', icon: '🛒', pay: 16, var: 6 },
    { id: 'athlete', name: 'Athlete', icon: '⚽', pay: 22, var: 14 },
  ];
  const COLLEGE_CAREERS = [
    { id: 'teacher', name: 'Teacher', icon: '📚', pay: 20, var: 0 },
    { id: 'lawyer', name: 'Lawyer', icon: '⚖️', pay: 28, var: 8 },
    { id: 'doctor', name: 'Doctor', icon: '🩺', pay: 34, var: 10 },
  ];
  const CB = {};                                     // career id -> career
  [...BASE_CAREERS, ...COLLEGE_CAREERS].forEach(c => { CB[c.id] = c; });
  const careersFor = seat_college => (seat_college ? COLLEGE_CAREERS : BASE_CAREERS);

  /* ordered milestone stops (by position); each maps to a decision phase */
  const STOPS = [
    { at: INS_AT, phase: 'insure', id: 'insDone' },
    { at: GAMBLE_AT[0], phase: 'gamble', id: 'g0' },
    { at: GAMBLE_AT[1], phase: 'gamble', id: 'g1' },
    { at: FINISH, phase: 'retire', id: 'retDone' },
  ];

  function log(n, msg) { n.log.push(msg); if (n.log.length > 4) n.log.shift(); }
  function netWorth(s, seat) { return s.cash[seat]; }

  function paydayAmount(rng, career) {
    const c = CB[career];
    if (!c.var) return c.pay;
    return c.pay + (ri(rng, 2 * c.var + 1) - c.var);
  }

  /* decide the seat's next phase from its position + resolved milestones */
  function setNextPhase(n, seat) {
    const f = n.flags[seat];
    let stop = null;
    for (const st of STOPS) {                        // lowest unresolved stop we've reached
      if (!f[st.id] && n.pos[seat] >= st.at) { stop = st; break; }
    }
    if (stop) { n.phase[seat] = stop.phase; n.stopId[seat] = stop.id; return; }
    if (f.retDone) { n.phase[seat] = 'done'; n.done[seat] = true; return; }
    n.phase[seat] = 'spin';
  }

  /* resolve all board effects crossed by a single spin */
  function resolveSpin(n, seat, rng) {
    const old = n.pos[seat];
    const dest = Math.min(old + n.spin, FINISH);
    for (let p = old + 1; p <= dest; p++) {
      if (p % PAYDAY === 0 && n.career[seat]) {
        const amt = paydayAmount(rng, n.career[seat]);
        n.cash[seat] += amt;
        log(n, `${tag(seat)} payday +$${amt}k`);
      }
      if (HAZARD_AT.includes(p) && !n.insured[seat]) {
        if (spin10(rng) <= 4) {                      // 40% chance of an accident
          n.cash[seat] -= HAZARD_COST;
          log(n, `${tag(seat)} accident -$${HAZARD_COST}k 🚑`);
        }
      }
      if (p === MARRY_AT) { n.cash[seat] += MARRY_GIFT; log(n, `${tag(seat)} gets married +$${MARRY_GIFT}k 💍`); }
      if (p === BABY_AT) { n.cash[seat] += BABY_GIFT; log(n, `${tag(seat)} has a baby +$${BABY_GIFT}k 👶`); }
    }
    n.pos[seat] = dest;
  }

  function tag(seat) { return seat === 0 ? 'You' : 'Bot'; }

  function nextActor(n, seat) {
    const other = 1 - seat;
    if (!n.done[other]) return other;
    if (!n.done[seat]) return seat;
    return other;
  }

  /* ---------- rule cards ---------- */
  const rules = [
    {
      id: 'college', name: 'Go to college', icon: '🎓', kind: 'pick',
      desc: 'Take the college fork -- a student loan now buys higher-tier careers later.',
      pick: (s, cands) => cands.find(m => m.type === 'fork' && m.path === 'college') ?? null,
    },
    {
      id: 'big-salary', name: 'Chase the big salary', icon: '💸', kind: 'pick',
      desc: 'At the career space, always take the highest-paying job on offer.',
      pick(s, cands) {
        const cs = cands.filter(m => m.type === 'career');
        if (!cs.length) return null;
        return cs.reduce((a, b) => (CB[a.career].pay >= CB[b.career].pay ? a : b));
      },
    },
    {
      id: 'steady', name: 'Steady paycheck', icon: '🧱', kind: 'pick',
      desc: 'Prefer the most predictable career -- lowest swing, no payday surprises.',
      pick(s, cands) {
        const cs = cands.filter(m => m.type === 'career');
        if (!cs.length) return null;
        return cs.reduce((a, b) => {
          const A = CB[a.career], B = CB[b.career];
          if (A.var !== B.var) return A.var <= B.var ? a : b;
          return A.pay >= B.pay ? a : b;
        });
      },
    },
    {
      id: 'insured', name: 'Always insured', icon: '🛡️', kind: 'pick',
      desc: 'Buy full insurance -- a fixed cost that waives every later hazard space.',
      pick: (s, cands) => cands.find(m => m.type === 'insure' && m.buy) ?? null,
    },
    {
      id: 'high-roller', name: 'High roller', icon: '🎰', kind: 'pick',
      desc: 'Play the stock market and bet retirement on Millionaire Estates.',
      pick(s, cands) {
        const bet = cands.find(m => m.type === 'gamble' && m.bet);
        if (bet) return bet;
        return cands.find(m => m.type === 'retire' && m.choice === 'estates') ?? null;
      },
    },
    {
      id: 'safe', name: 'Play it safe', icon: '🔒', kind: 'avoid',
      desc: 'Never gamble on the stock market; retire to guaranteed Countryside Acres.',
      avoid: (s, m) =>
        (m.type === 'gamble' && m.bet) || (m.type === 'retire' && m.choice === 'estates'),
    },
  ];

  StrategyLab.registerGame({
    id: 'life',
    name: 'The Game of Life',
    icon: '🌡️',
    level: 'Intermediate',
    tagline: 'College or career, safe or bold -- spin the wheel and grow your net worth.',
    rules,

    botPresets: [
      {
        id: 'randy', name: 'Randy Rookie', icon: '🐣', stars: 1,
        desc: 'Spins the wheel and shrugs at every fork in the road.', ruleIds: [],
      },
      {
        id: 'stan', name: 'Steady Stan', icon: '🧱', stars: 2,
        desc: 'Skips college, takes a safe job, never gambles a cent.',
        ruleIds: ['steady', 'safe'],
      },
      {
        id: 'clara', name: 'Climber Clara', icon: '🎓', stars: 3,
        desc: 'College, the best salary she can get, and full insurance.',
        ruleIds: ['college', 'big-salary', 'insured'],
      },
      {
        id: 'vera', name: 'Venture Vera', icon: '💼', stars: 4,
        desc: 'A doctorate, top pay, insured against hazards, and bold at the market.',
        ruleIds: ['college', 'big-salary', 'insured', 'high-roller'],
      },
    ],

    maxTurns: 2000,

    initialState(rng, firstSeat) {
      return {
        pos: [0, 0], cash: [0, 0],
        college: [false, false], career: [null, null], insured: [false, false],
        phase: ['fork', 'fork'], stopId: [null, null], done: [false, false],
        flags: [{}, {}],
        current: firstSeat, spin: spin10(rng), log: [],
      };
    },
    currentPlayer: s => s.current,

    legalMoves(s) {
      const seat = s.current;
      switch (s.phase[seat]) {
        case 'fork':
          return [{ type: 'fork', path: 'college' }, { type: 'fork', path: 'career' }];
        case 'career':
          return careersFor(s.college[seat]).map(c => ({ type: 'career', career: c.id }));
        case 'insure':
          return [{ type: 'insure', buy: true }, { type: 'insure', buy: false }];
        case 'gamble':
          return [{ type: 'gamble', bet: true }, { type: 'gamble', bet: false }];
        case 'retire':
          return [{ type: 'retire', choice: 'country' }, { type: 'retire', choice: 'estates' }];
        default:
          return [{ type: 'spin' }];
      }
    },

    applyMove(s, move, rng) {
      const n = StrategyLab.clone(s);
      n.log = [];
      const seat = n.current;
      if (move) {
        if (move.type === 'fork') {
          if (move.path === 'college') {
            n.college[seat] = true; n.cash[seat] -= TUITION;
            log(n, `${tag(seat)} enrolls in college -$${TUITION}k`);
          } else {
            log(n, `${tag(seat)} starts working right away`);
          }
          n.phase[seat] = 'career';
        } else if (move.type === 'career') {
          n.career[seat] = move.career;
          log(n, `${tag(seat)} becomes a ${CB[move.career].name}`);
          setNextPhase(n, seat);
        } else if (move.type === 'insure') {
          if (move.buy) {
            n.insured[seat] = true; n.cash[seat] -= INSURANCE_COST;
            log(n, `${tag(seat)} buys insurance -$${INSURANCE_COST}k`);
          } else {
            log(n, `${tag(seat)} skips insurance`);
          }
          n.flags[seat][n.stopId[seat]] = true;
          setNextPhase(n, seat);
        } else if (move.type === 'gamble') {
          if (move.bet) {
            if (spin10(rng) >= 6) {
              n.cash[seat] += GAMBLE_WIN;
              log(n, `${tag(seat)} wins big at the market +$${GAMBLE_WIN}k`);
            } else {
              n.cash[seat] -= GAMBLE_LOSE;
              log(n, `${tag(seat)} loses at the market -$${GAMBLE_LOSE}k`);
            }
          } else {
            log(n, `${tag(seat)} stays out of the market`);
          }
          n.flags[seat][n.stopId[seat]] = true;
          setNextPhase(n, seat);
        } else if (move.type === 'retire') {
          if (move.choice === 'country') {
            n.cash[seat] += COUNTRY;
            log(n, `${tag(seat)} retires to Countryside Acres +$${COUNTRY}k`);
          } else {
            const payout = spin10(rng) * ESTATE_PER;
            n.cash[seat] += payout;
            log(n, `${tag(seat)} cashes out Millionaire Estates +$${payout}k`);
          }
          n.flags[seat].retDone = true;
          n.phase[seat] = 'done'; n.done[seat] = true;
        } else {                                     // 'spin' -> advance
          resolveSpin(n, seat, rng);
          setNextPhase(n, seat);
        }
      }
      n.current = nextActor(n, seat);
      n.spin = spin10(rng);
      return n;
    },

    isTerminal: s => s.done[0] && s.done[1],
    winner(s) {
      const a = netWorth(s, 0), b = netWorth(s, 1);
      return a === b ? null : a > b ? 0 : 1;
    },
    timeoutWinner(s) {
      const a = netWorth(s, 0), b = netWorth(s, 1);
      return a === b ? null : a > b ? 0 : 1;
    },

    describeMove(s, move, seat) {
      if (!move) return 'waits';
      switch (move.type) {
        case 'fork':
          return move.path === 'college'
            ? `heads to college on a $${TUITION}k student loan 🎓`
            : 'skips college and starts working right away 💼';
        case 'career': {
          const c = CB[move.career];
          return `takes the ${c.name} ${c.icon} career ($${c.pay}k/payday)`;
        }
        case 'insure':
          return move.buy
            ? `buys full insurance for $${INSURANCE_COST}k 🛡️`
            : 'declines insurance and hopes for the best';
        case 'gamble':
          return move.bet
            ? 'risks cash on the stock market 🎰'
            : 'walks past the stock market, unmoved';
        case 'retire':
          return move.choice === 'country'
            ? `retires to Countryside Acres (+$${COUNTRY}k) 🏡`
            : 'bets it all on Millionaire Estates 🎰';
        default:
          return `spins a ${s.spin} and drives on 🎡`;
      }
    },

    renderState(s, el) {
      const W = 268, H = 132, x0 = 16, x1 = 252, ty = 74;
      const mapX = p => x0 + (p / FINISH) * (x1 - x0);
      const MILES = [
        { p: 0, e: '🏁' },
        { p: INS_AT, e: '🛡️' },
        { p: GAMBLE_AT[0], e: '🎰' },
        { p: GAMBLE_AT[1], e: '🎰' },
        { p: FINISH, e: '🏡' },
      ];
      const COL = ['#3b82f6', '#ef4444'];

      let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%">`;
      svg += `<line x1="${x0}" y1="${ty}" x2="${x1}" y2="${ty}" ` +
        `stroke="#cbd2dc" stroke-width="8" stroke-linecap="round"/>`;
      for (let p = PAYDAY; p < FINISH; p += PAYDAY) {   // payday ticks
        const x = mapX(p).toFixed(1);
        svg += `<line x1="${x}" y1="${ty - 6}" x2="${x}" y2="${ty + 6}" stroke="#7c8aa0" stroke-width="2"/>`;
      }
      for (const m of MILES) {
        const x = mapX(m.p).toFixed(1);
        svg += `<circle cx="${x}" cy="${ty}" r="7" fill="#f4f6fa" stroke="#7c8aa0" stroke-width="2"/>`;
        svg += `<text x="${x}" y="${ty - 16}" text-anchor="middle" font-size="13">${m.e}</text>`;
      }
      for (const seat of [0, 1]) {
        const x = mapX(s.pos[seat]).toFixed(1);
        const y = seat === 0 ? ty - 11 : ty + 11;
        svg += `<circle cx="${x}" cy="${y}" r="6" fill="${COL[seat]}" stroke="#fff" stroke-width="2"/>`;
      }
      svg += `<text x="${x0}" y="20" font-size="13">🎡 ${s.spin}</text>`;
      svg += '</svg>';

      const careerText = seat => {
        if (s.career[seat]) { const c = CB[s.career[seat]]; return `${c.icon} ${c.name}`; }
        return s.college[seat] ? 'in college 🎓' : 'starting out';
      };
      const stageText = seat => {
        if (s.done[seat]) return 'retired 🏁';
        return {
          fork: 'choosing a path', career: 'choosing a career', insure: 'insurance?',
          gamble: 'at the market', retire: 'retiring',
        }[s.phase[seat]] || 'on the road';
      };
      const row = seat =>
        `<div><span class="lab${seat}">●</span> ${seat === 0 ? 'You' : 'Bot'}: ` +
        `<b>$${netWorth(s, seat)}k</b> · ${careerText(seat)} · ${stageText(seat)}</div>`;

      el.innerHTML = svg +
        `<div class="board-status">${row(0)}${row(1)}` +
        (s.log.length ? `<div class="game-log">${s.log.join('<br>')}</div>` : '') +
        `</div>`;
    },

    insight({ userWins, botWins, n, userRuleIds }) {
      const hasIncome = userRuleIds.includes('college') || userRuleIds.includes('big-salary');
      if (!hasIncome && userWins < botWins) {
        return 'Net worth is mostly salary times paydays. Without a career card you take whatever ' +
          'job the random fallback lands on -- add "Go to college" and "Chase the big salary" and ' +
          'the income gap does the rest. The gambles are just noise on top.';
      }
      if (userWins > botWins && userWins >= n * 0.62) {
        return 'Convincing. The big lever here is expected income (college + top salary), not the ' +
          'spinner. Insurance trims your downside, and the stock market plus Millionaire Estates ' +
          'are slightly positive-EV bets -- worth taking once your salary already leads.';
      }
      if (Math.abs(userWins - botWins) <= 10) {
        return 'Nearly even -- two sensible income plans converge, and from there the spinner, the ' +
          'hazards and the retirement gamble add variance that no card can steer. Recognizing where ' +
          'skill stops and luck takes over is a strategy insight in itself.';
      }
      return null;
    },
  });
})();
