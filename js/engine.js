/* ============================================================
 * Strategy Lab — core engine
 *
 * A "strategy" is an ordered list of rule ids (the stack).
 * Each turn the stack is read top to bottom:
 *   - PICK  rules may choose one move from the current candidates
 *   - AVOID rules veto candidate moves (unless that would veto all)
 * The first PICK rule that decides, decides. If nothing decides,
 * a random legal move is played ("Lucky pick").
 *
 * Games register themselves via StrategyLab.registerGame(game).
 * See README.md for the full game interface.
 * ============================================================ */
window.StrategyLab = (function () {
  'use strict';

  /* ---------- deterministic RNG (mulberry32) ----------
   * Every game of a match gets its own seed, so any game can be
   * re-simulated later (with full recording) for the replay viewer. */
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function randInt(rng, n) { return Math.floor(rng() * n); }
  function pickRandom(rng, arr) { return arr[randInt(rng, arr.length)]; }
  function clone(s) { return JSON.parse(JSON.stringify(s)); }

  const games = [];
  function registerGame(g) { games.push(g); }
  function getGame(id) { return games.find(g => g.id === id); }

  function resolveStack(game, ruleIds) {
    return (ruleIds || [])
      .map(id => game.rules.find(r => r.id === id))
      .filter(Boolean);
  }

  /* ---------- policy evaluation ---------- */
  function chooseMove(game, state, stack, seat, rng) {
    let candidates = game.legalMoves(state);
    if (candidates.length === 0) return null;            // pass
    for (const rule of stack) {
      if (candidates.length === 1) break;
      if (rule.kind === 'avoid') {
        const kept = candidates.filter(m => !rule.avoid(state, m, seat));
        if (kept.length > 0) candidates = kept;          // never veto everything
      } else {
        const m = rule.pick(state, candidates, seat, rng);
        if (m !== null && m !== undefined) return m;
      }
    }
    return candidates.length === 1 ? candidates[0] : pickRandom(rng, candidates);
  }

  /* ---------- one full game ---------- */
  function playGame(game, stacks, firstSeat, seed, record) {
    const rng = mulberry32(seed);
    let state = game.initialState(rng, firstSeat);
    const replay = record ? [{ state: clone(state), caption: 'Game start', seat: null }] : null;
    const maxTurns = game.maxTurns || 2000;
    let turns = 0;

    while (!game.isTerminal(state) && turns < maxTurns) {
      const seat = game.currentPlayer(state);
      const move = chooseMove(game, state, stacks[seat], seat, rng);
      const caption = record ? game.describeMove(state, move, seat) : null;
      state = game.applyMove(state, move, rng);
      if (record) replay.push({ state: clone(state), caption, seat });
      turns++;
    }

    let winner = null, timeout = false;
    if (game.isTerminal(state)) {
      winner = game.winner(state);
    } else {
      timeout = true;
      winner = game.timeoutWinner ? game.timeoutWinner(state) : null;
    }
    return { winner, turns, replay, timeout };
  }

  /* ---------- a match = n games, alternating who starts ---------- */
  function simulateMatch(game, userRuleIds, botRuleIds, nGames, baseSeed) {
    const stacks = [resolveStack(game, userRuleIds), resolveStack(game, botRuleIds)];
    const results = [];
    for (let i = 0; i < nGames; i++) {
      const r = playGame(game, stacks, i % 2, (baseSeed + i * 7919) >>> 0, false);
      results.push({ winner: r.winner, turns: r.turns, timeout: r.timeout, firstSeat: i % 2 });
    }
    return { results, baseSeed };
  }

  /* Re-simulate one specific game of a match with full recording. */
  function replayGame(game, userRuleIds, botRuleIds, gameIndex, baseSeed) {
    const stacks = [resolveStack(game, userRuleIds), resolveStack(game, botRuleIds)];
    return playGame(game, stacks, gameIndex % 2, (baseSeed + gameIndex * 7919) >>> 0, true);
  }

  return {
    games, registerGame, getGame,
    simulateMatch, replayGame, resolveStack,
    chooseMove, playGame,
    mulberry32, randInt, pickRandom, clone,
  };
})();
