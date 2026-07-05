/* ============================================================
 * Monopoly — 2-player duel on the classic 40-square board.
 * The dice turns run automatically; your strategy answers the
 * only three questions that matter: buy it? build on it? pay
 * your way out of jail?
 *
 * Simplifications: no auctions, no trading between players, no
 * mortgages (forced sales at half price instead), max 4 houses
 * (no hotels), an approximated rent curve (base × 1/5/15/30/40),
 * and compact Chance/Community-Chest decks. A game ends by
 * bankruptcy or after 60 rounds each (net worth decides).
 * ============================================================ */
(function () {
  'use strict';

  const ri = StrategyLab.randInt;

  /* t: go|prop|rr|util|tax|chance|chest|jail|gotojail|free
   * g: color group 0..7 · p: price · r: base rent */
  const SQ = [
    { n: 'GO', t: 'go' },
    { n: 'Mediterranean Ave', t: 'prop', g: 0, p: 60, r: 2 },
    { n: 'Community Chest', t: 'chest' },
    { n: 'Baltic Ave', t: 'prop', g: 0, p: 60, r: 4 },
    { n: 'Income Tax', t: 'tax', amt: 200 },
    { n: 'Reading Railroad', t: 'rr', p: 200 },
    { n: 'Oriental Ave', t: 'prop', g: 1, p: 100, r: 6 },
    { n: 'Chance', t: 'chance' },
    { n: 'Vermont Ave', t: 'prop', g: 1, p: 100, r: 6 },
    { n: 'Connecticut Ave', t: 'prop', g: 1, p: 120, r: 8 },
    { n: 'Jail — Just Visiting', t: 'jail' },
    { n: 'St. Charles Place', t: 'prop', g: 2, p: 140, r: 10 },
    { n: 'Electric Company', t: 'util', p: 150 },
    { n: 'States Ave', t: 'prop', g: 2, p: 140, r: 10 },
    { n: 'Virginia Ave', t: 'prop', g: 2, p: 160, r: 12 },
    { n: 'Pennsylvania Railroad', t: 'rr', p: 200 },
    { n: 'St. James Place', t: 'prop', g: 3, p: 180, r: 14 },
    { n: 'Community Chest', t: 'chest' },
    { n: 'Tennessee Ave', t: 'prop', g: 3, p: 180, r: 14 },
    { n: 'New York Ave', t: 'prop', g: 3, p: 200, r: 16 },
    { n: 'Free Parking', t: 'free' },
    { n: 'Kentucky Ave', t: 'prop', g: 4, p: 220, r: 18 },
    { n: 'Chance', t: 'chance' },
    { n: 'Indiana Ave', t: 'prop', g: 4, p: 220, r: 18 },
    { n: 'Illinois Ave', t: 'prop', g: 4, p: 240, r: 20 },
    { n: 'B&O Railroad', t: 'rr', p: 200 },
    { n: 'Atlantic Ave', t: 'prop', g: 5, p: 260, r: 22 },
    { n: 'Ventnor Ave', t: 'prop', g: 5, p: 260, r: 22 },
    { n: 'Water Works', t: 'util', p: 150 },
    { n: 'Marvin Gardens', t: 'prop', g: 5, p: 280, r: 24 },
    { n: 'Go To Jail', t: 'gotojail' },
    { n: 'Pacific Ave', t: 'prop', g: 6, p: 300, r: 26 },
    { n: 'North Carolina Ave', t: 'prop', g: 6, p: 300, r: 26 },
    { n: 'Community Chest', t: 'chest' },
    { n: 'Pennsylvania Ave', t: 'prop', g: 6, p: 320, r: 28 },
    { n: 'Short Line Railroad', t: 'rr', p: 200 },
    { n: 'Chance', t: 'chance' },
    { n: 'Park Place', t: 'prop', g: 7, p: 350, r: 35 },
    { n: 'Luxury Tax', t: 'tax', amt: 100 },
    { n: 'Boardwalk', t: 'prop', g: 7, p: 400, r: 50 },
  ];
  const GROUP_COLORS = ['#8d5a2b', '#9bd6f0', '#d167b5', '#f0a33c',
    '#e05252', '#f2dd55', '#4fbf73', '#5b8df0'];
  const GROUPS = [[], [], [], [], [], [], [], []];
  SQ.forEach((sq, i) => { if (sq.t === 'prop') GROUPS[sq.g].push(i); });
  const RRS = SQ.map((sq, i) => (sq.t === 'rr' ? i : -1)).filter(i => i >= 0);
  const UTILS = SQ.map((sq, i) => (sq.t === 'util' ? i : -1)).filter(i => i >= 0);
  const HCOST = g => [50, 50, 100, 100, 150, 150, 200, 200][g];
  const MULT = [1, 5, 15, 30, 40];
  const MAX_ROUNDS = 120;                 // total turn-starts (60 per player)
  const RESERVE = 300;                    // "Cash cushion" threshold

  const tag = p => (p === 0 ? 'You' : 'Bot');
  function log(n, msg) { n.log.push(msg); if (n.log.length > 7) n.log.shift(); }

  function groupComplete(n, g, seat) { return GROUPS[g].every(i => n.owner[i] === seat); }
  function calcRent(n, sq) {
    const o = n.owner[sq], def = SQ[sq];
    if (def.t === 'rr') {
      const cnt = RRS.filter(i => n.owner[i] === o).length;
      return 25 * Math.pow(2, cnt - 1);
    }
    if (def.t === 'util') {
      const both = UTILS.every(i => n.owner[i] === o);
      return (both ? 10 : 4) * n.lastRoll;
    }
    if (n.houses[sq] > 0) return def.r * MULT[n.houses[sq]];
    return groupComplete(n, def.g, o) ? def.r * 2 : def.r;
  }
  function buildCandidates(n, p) {
    const out = [];
    for (let i = 0; i < 40; i++) {
      const d = SQ[i];
      if (d.t !== 'prop' || n.owner[i] !== p || n.houses[i] >= 4) continue;
      if (!groupComplete(n, d.g, p)) continue;
      if (n.cash[p] < HCOST(d.g)) continue;
      out.push(i);
    }
    return out;
  }
  function netWorth(n, p) {
    let w = n.cash[p];
    for (let i = 0; i < 40; i++) {
      if (n.owner[i] === p) w += SQ[i].p + n.houses[i] * HCOST(SQ[i].g || 0);
    }
    return w;
  }

  function goJail(n, p) {
    n.pos[p] = 10; n.jail[p] = true; n.jailT[p] = 0; n.extra = false;
  }
  function charge(n, p, amount, toSeat) {
    n.cash[p] -= amount;
    if (toSeat >= 0) n.cash[toSeat] += amount;
    while (n.cash[p] < 0) {              // forced liquidation, half price
      let best = -1;
      for (let i = 0; i < 40; i++) {     // sell the most expensive house first
        if (n.owner[i] === p && n.houses[i] > 0 &&
          (best === -1 || HCOST(SQ[i].g) > HCOST(SQ[best].g))) best = i;
      }
      if (best !== -1) {
        n.houses[best]--; n.cash[p] += HCOST(SQ[best].g) / 2;
        log(n, `${tag(p)} sells a house on ${SQ[best].n}`);
        continue;
      }
      for (let i = 0; i < 40; i++) {     // then the cheapest property
        if (n.owner[i] === p && (best === -1 || SQ[i].p < SQ[best].p)) best = i;
      }
      if (best !== -1) {
        n.owner[best] = -1; n.cash[p] += SQ[best].p / 2;
        log(n, `${tag(p)} sells ${SQ[best].n} to the bank`);
        continue;
      }
      n.dead = p;
      log(n, `${tag(p)} is bankrupt! 💥`);
      break;
    }
  }

  function rollMove(n, p, rng) {
    const d1 = 1 + ri(rng, 6), d2 = 1 + ri(rng, 6);
    n.lastRoll = d1 + d2;
    n.extra = d1 === d2;
    if (d1 === d2) {
      n.doubles++;
      if (n.doubles >= 3) {
        log(n, `${tag(p)} rolls a third double — straight to jail 🚔`);
        goJail(n, p); n.phase = 'next';
        return;
      }
    }
    if (n.pos[p] + n.lastRoll >= 40) { n.cash[p] += 200; log(n, `${tag(p)} passes GO +$200`); }
    n.pos[p] = (n.pos[p] + n.lastRoll) % 40;
    log(n, `${tag(p)} rolls ${d1}·${d2} → ${SQ[n.pos[p]].n}`);
    land(n, p, rng);
  }

  function land(n, p, rng) {
    const sq = n.pos[p], def = SQ[sq];
    if (def.t === 'prop' || def.t === 'rr' || def.t === 'util') {
      const o = n.owner[sq];
      if (o === -1) {
        if (n.cash[p] >= def.p) { n.phase = 'buy'; n.buySq = sq; return; }
        log(n, `${tag(p)} can't afford ${def.n}`);
      } else if (o !== p) {
        const rent = calcRent(n, sq);
        log(n, `${tag(p)} pays $${rent} rent for ${def.n}`);
        charge(n, p, rent, o);
      }
      n.phase = 'after'; return;
    }
    if (def.t === 'tax') {
      log(n, `${tag(p)} pays $${def.amt} ${def.n}`);
      charge(n, p, def.amt, -1);
      n.phase = 'after'; return;
    }
    if (def.t === 'gotojail') {
      log(n, `${tag(p)} is sent to jail 🚔`);
      goJail(n, p); n.phase = 'next'; return;
    }
    if (def.t === 'chance' || def.t === 'chest') { drawCard(n, p, rng); return; }
    n.phase = 'after';                   // go / jail visit / free parking
  }

  function drawCard(n, p, rng) {
    const card = ri(rng, 8);
    if (card <= 2) {
      const amt = [200, 100, 50][card];
      n.cash[p] += amt; log(n, `${tag(p)} draws a card: +$${amt}`);
    } else if (card <= 4) {
      const amt = card === 3 ? 50 : 100;
      log(n, `${tag(p)} draws a card: pay $${amt}`);
      charge(n, p, amt, -1);
    } else if (card === 5) {
      n.pos[p] = 0; n.cash[p] += 200;
      log(n, `${tag(p)} advances to GO +$200`);
    } else if (card === 6) {
      log(n, `${tag(p)} draws: go directly to jail 🚔`);
      goJail(n, p); n.phase = 'next'; return;
    } else {
      let h = 0;
      for (let i = 0; i < 40; i++) if (n.owner[i] === p) h += n.houses[i];
      log(n, `${tag(p)} pays street repairs: $${h * 25}`);
      if (h) charge(n, p, h * 25, -1);
    }
    n.phase = 'after';
  }

  function jailWait(n, p, rng) {
    const d1 = 1 + ri(rng, 6), d2 = 1 + ri(rng, 6);
    n.lastRoll = d1 + d2;
    n.extra = false;
    if (d1 === d2) {
      n.jail[p] = false;
      log(n, `${tag(p)} rolls doubles and walks out of jail!`);
      n.pos[p] = 10 + n.lastRoll;
      land(n, p, rng);
      return;
    }
    n.jailT[p]++;
    if (n.jailT[p] >= 3) {
      log(n, `${tag(p)} pays the $50 fine after three tries`);
      charge(n, p, 50, -1);
      if (n.dead !== -1) return;
      n.jail[p] = false;
      n.pos[p] = 10 + n.lastRoll;
      land(n, p, rng);
      return;
    }
    log(n, `${tag(p)} fails to roll doubles, stays in jail`);
    n.phase = 'next';
  }

  /* run the turn machine until a decision is needed or the game ends */
  function advance(n, rng) {
    let guard = 0;
    while (guard++ < 2000) {
      if (n.dead !== -1 || n.rounds >= MAX_ROUNDS) return;
      if (n.phase === 'jail' || n.phase === 'buy' || n.phase === 'build') return;
      const p = n.current;
      if (n.phase === 'start') {
        n.rounds++; n.doubles = 0;
        if (n.jail[p]) {
          if (n.cash[p] >= 50) { n.phase = 'jail'; return; }
          jailWait(n, p, rng);
        } else {
          rollMove(n, p, rng);
        }
      } else if (n.phase === 'after') {
        if (buildCandidates(n, p).length > 0) { n.phase = 'build'; return; }
        n.phase = 'endroll';
      } else if (n.phase === 'endroll') {
        if (n.extra && !n.jail[p] && n.dead === -1) rollMove(n, p, rng);
        else n.phase = 'next';
      } else if (n.phase === 'next') {
        n.current = 1 - p; n.phase = 'start';
      } else {
        return;
      }
    }
  }

  /* ---------- rule cards ---------- */
  const wantBuy = (s, cands) => cands.find(m => m.t === 'buy') ?? null;
  const rules = [
    {
      id: 'buy-all', name: 'Buy it all', icon: '🛍️', kind: 'pick',
      desc: 'If it is for sale and you can pay, buy it. No exceptions.',
      pick: (s, cands) => (s.phase === 'buy' ? wantBuy(s, cands) : null),
    },
    {
      id: 'set-hunter', name: 'Set hunter', icon: '🎯', kind: 'pick',
      desc: 'Buy streets in color groups you already started.',
      pick(s, cands, seat) {
        if (s.phase !== 'buy' || SQ[s.buySq].t !== 'prop') return null;
        const g = SQ[s.buySq].g;
        return GROUPS[g].some(i => i !== s.buySq && s.owner[i] === seat)
          ? wantBuy(s, cands) : null;
      },
    },
    {
      id: 'blocker', name: 'Block their set', icon: '🚫', kind: 'pick',
      desc: 'Buy streets the opponent needs to complete a color group.',
      pick(s, cands, seat) {
        if (s.phase !== 'buy' || SQ[s.buySq].t !== 'prop') return null;
        const g = SQ[s.buySq].g;
        return GROUPS[g].some(i => s.owner[i] === 1 - seat)
          ? wantBuy(s, cands) : null;
      },
    },
    {
      id: 'tycoon', name: 'Rail tycoon', icon: '🚂', kind: 'pick',
      desc: 'Always buy railroads and utilities — steady income.',
      pick(s, cands) {
        if (s.phase !== 'buy') return null;
        const t = SQ[s.buySq].t;
        return t === 'rr' || t === 'util' ? wantBuy(s, cands) : null;
      },
    },
    {
      id: 'bargain', name: 'Bargain bin', icon: '🏷️', kind: 'pick',
      desc: 'Buy anything priced $200 or less.',
      pick: (s, cands) =>
        (s.phase === 'buy' && SQ[s.buySq].p <= 200 ? wantBuy(s, cands) : null),
    },
    {
      id: 'cushion', name: 'Cash cushion', icon: '💰', kind: 'avoid',
      desc: `Veto purchases and houses that drop you below $${RESERVE}.`,
      avoid(s, m, seat) {
        if (m.t === 'buy') return s.cash[seat] - SQ[s.buySq].p < RESERVE;
        if (m.t === 'house') return s.cash[seat] - HCOST(SQ[m.sq].g) < RESERVE;
        return false;
      },
    },
    {
      id: 'builder', name: 'Master builder', icon: '🏗️', kind: 'pick',
      desc: 'Build houses on your priciest streets first — rent explodes.',
      pick(s, cands) {
        const hs = cands.filter(m => m.t === 'house');
        if (!hs.length) return null;
        return hs.reduce((a, b) => (SQ[a.sq].r >= SQ[b.sq].r ? a : b));
      },
    },
    {
      id: 'spread', name: 'Even spread', icon: '🌱', kind: 'pick',
      desc: 'Build the cheapest, least developed house first.',
      pick(s, cands) {
        const hs = cands.filter(m => m.t === 'house');
        if (!hs.length) return null;
        const score = m => s.houses[m.sq] * 1000 + HCOST(SQ[m.sq].g);
        return hs.reduce((a, b) => (score(a) <= score(b) ? a : b));
      },
    },
    {
      id: 'pay-jail', name: 'Bail out', icon: '🔓', kind: 'pick',
      desc: 'Pay the $50 immediately — time is money.',
      pick: (s, cands) => (s.phase === 'jail' ? cands.find(m => m.t === 'pay') ?? null : null),
    },
    {
      id: 'sit-jail', name: 'Cozy cell', icon: '🛏️', kind: 'pick',
      desc: "Stay put and roll for doubles — jail is rent-free real estate.",
      pick: (s, cands) => (s.phase === 'jail' ? cands.find(m => m.t === 'wait') ?? null : null),
    },
  ];

  StrategyLab.registerGame({
    id: 'monopoly',
    name: 'Monopoly',
    icon: '🎩',
    level: 'Advanced',
    tagline: 'Buy, build, bankrupt — answer the three questions that matter.',
    rules,

    botPresets: [
      {
        id: 'randy', name: 'Randy Rookie', icon: '🐣', stars: 1,
        desc: 'Flips a coin for every purchase. Lands on Boardwalk, shrugs.', ruleIds: [],
      },
      {
        id: 'tina', name: 'Tina Tightwad', icon: '🪙', stars: 2,
        desc: 'Never spends a dollar she does not absolutely have to.',
        ruleIds: ['cushion', 'bargain', 'spread', 'sit-jail'],
      },
      {
        id: 'bobby', name: 'Bobby Buy-It-All', icon: '🛍️', stars: 3,
        desc: 'If it is for sale, it is his. Houses on everything.',
        ruleIds: ['buy-all', 'builder', 'pay-jail'],
      },
      {
        id: 'mona', name: 'Mogul Mona', icon: '💼', stars: 4,
        desc: 'Sets, denial, railroads, houses — in exactly that order.',
        ruleIds: ['set-hunter', 'blocker', 'tycoon', 'builder', 'cushion', 'bargain', 'sit-jail'],
      },
    ],

    maxTurns: 4000,

    initialState(rng, firstSeat) {
      const n = {
        pos: [0, 0], cash: [1500, 1500],
        owner: Array(40).fill(-1), houses: Array(40).fill(0),
        jail: [false, false], jailT: [0, 0],
        extra: false, doubles: 0, lastRoll: 7,
        phase: 'start', buySq: -1, current: firstSeat,
        rounds: 0, dead: -1, log: [],
      };
      advance(n, rng);
      return n;
    },
    currentPlayer: s => s.current,

    legalMoves(s) {
      if (s.phase === 'jail') return [{ t: 'pay' }, { t: 'wait' }];
      if (s.phase === 'buy') return [{ t: 'buy' }, { t: 'skip' }];
      if (s.phase === 'build') {
        return buildCandidates(s, s.current).map(sq => ({ t: 'house', sq }))
          .concat([{ t: 'done' }]);
      }
      return [];
    },

    applyMove(s, move, rng) {
      const n = StrategyLab.clone(s);
      n.log = [];
      const p = n.current;
      if (move) {
        if (move.t === 'pay') {
          n.cash[p] -= 50; n.jail[p] = false;
          log(n, `${tag(p)} pays $50 bail`);
          rollMove(n, p, rng);
        } else if (move.t === 'wait') {
          jailWait(n, p, rng);
        } else if (move.t === 'buy') {
          n.cash[p] -= SQ[n.buySq].p; n.owner[n.buySq] = p;
          log(n, `${tag(p)} buys ${SQ[n.buySq].n} for $${SQ[n.buySq].p}`);
          n.phase = 'after';
        } else if (move.t === 'skip') {
          log(n, `${tag(p)} passes on ${SQ[n.buySq].n}`);
          n.phase = 'after';
        } else if (move.t === 'house') {
          n.cash[p] -= HCOST(SQ[move.sq].g); n.houses[move.sq]++;
          log(n, `${tag(p)} builds on ${SQ[move.sq].n} (now ${n.houses[move.sq]} 🏠)`);
          if (buildCandidates(n, p).length === 0) n.phase = 'endroll';
        } else if (move.t === 'done') {
          n.phase = 'endroll';
        }
      }
      advance(n, rng);
      return n;
    },

    isTerminal: s => s.dead !== -1 || s.rounds >= MAX_ROUNDS,
    winner(s) {
      if (s.dead !== -1) return 1 - s.dead;
      const a = netWorth(s, 0), b = netWorth(s, 1);
      return a === b ? null : a > b ? 0 : 1;
    },
    timeoutWinner(s) { return this.winner(s); },

    describeMove(s, move, seat) {
      if (!move) return 'continues';
      if (move.t === 'pay') return 'pays the $50 bail and rolls';
      if (move.t === 'wait') return 'sits tight in jail, hoping for doubles';
      if (move.t === 'buy') return `buys ${SQ[s.buySq].n} for $${SQ[s.buySq].p}`;
      if (move.t === 'skip') return `passes on ${SQ[s.buySq].n}`;
      if (move.t === 'house') return `builds a house on ${SQ[move.sq].n}`;
      return 'stops building';
    },

    renderState(s, el) {
      const rc = sq => (sq <= 10 ? [10, 10 - sq] : sq <= 20 ? [20 - sq, 0]
        : sq <= 30 ? [0, sq - 20] : [sq - 30, 10]);
      const GLYPH = {
        go: '🏁', jail: '🚔', free: '🅿️', gotojail: '👮',
        chance: '❓', chest: '🎁', tax: '💸', rr: '🚂', util: '💡',
      };
      let html = '<div class="mono-board">';
      for (let i = 0; i < 40; i++) {
        const d = SQ[i], [r, c] = rc(i);
        const own = s.owner[i] !== -1 ? ` own${s.owner[i]}` : '';
        let inner = '';
        if (d.t === 'prop') inner += `<i style="background:${GROUP_COLORS[d.g]}"></i>`;
        else inner += `<b>${GLYPH[d.t] || ''}</b>`;
        if (s.houses[i]) inner += `<em>${'▪'.repeat(s.houses[i])}</em>`;
        if (s.pos[0] === i) inner += '<s class="tk0"></s>';
        if (s.pos[1] === i) inner += '<s class="tk1"></s>';
        const title = d.p ? `${d.n} — $${d.p}` : d.n;
        html += `<div class="m-cell${own}" title="${title}" ` +
          `style="grid-row:${r + 1};grid-column:${c + 1}">${inner}</div>`;
      }
      html += `<div class="mono-center">` +
        `<div><span class="lab0">●</span> You <b>$${s.cash[0]}</b>${s.jail[0] ? ' 🚔' : ''}</div>` +
        `<div><span class="lab1">●</span> Bot <b>$${s.cash[1]}</b>${s.jail[1] ? ' 🚔' : ''}</div>` +
        `<div class="m-round">round ${Math.min(60, Math.ceil(s.rounds / 2))}/60 · 🎲 ${s.lastRoll}</div>` +
        (s.log.length ? `<div class="game-log">${s.log.join('<br>')}</div>` : '') +
        `</div></div>`;
      el.innerHTML = html;
    },

    insight({ userWins, botWins, n, userRuleIds }) {
      const buys = ['buy-all', 'set-hunter', 'blocker', 'tycoon', 'bargain'];
      if (!userRuleIds.some(id => buys.includes(id)) && userWins < botWins) {
        return 'Without a single buy card you only acquire property when the random fallback ' +
          'feels like it. In Monopoly, whoever owns the board owns the game — add a buying ' +
          'rule and watch the curve flip.';
      }
      if (userWins > botWins && userWins - botWins > 25) {
        return 'A landslide — your buying and building priorities are clearly sharper. One ' +
          'subtlety this simulation rewards: forced sales happen at half price, so a cash ' +
          'cushion is not cowardice, it is loss insurance.';
      }
      if (Math.abs(userWins - botWins) <= 10) {
        return 'Nearly even — and that is the honest truth about 2-player Monopoly without ' +
          'trading: any sensible buying policy lands within a few percent of any other. The ' +
          'dice own this board; the famous knife-fights only start when humans negotiate.';
      }
      return null;
    },
  });
})();
