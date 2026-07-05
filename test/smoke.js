/* Headless sanity tests: node test/smoke.js */
'use strict';
global.window = global;
require('../js/engine.js');
require('../js/games/tictactoe.js');
require('../js/games/snakes.js');
require('../js/games/maedn.js');
require('../js/games/monopoly.js');
// Catan is now engine-backed (catanatron); tested in server/test_policy.py.

const SL = window.StrategyLab;
let fails = 0;

function check(name, cond, extra) {
  console.log((cond ? 'PASS' : 'FAIL') + '  ' + name + (extra ? '   ' + extra : ''));
  if (!cond) fails++;
}

function run(gameId, userIds, botIds, n, seed = 12345) {
  const g = SL.getGame(gameId);
  const { results } = SL.simulateMatch(g, userIds, botIds, n, seed);
  let u = 0, b = 0, d = 0, t = 0, timeouts = 0;
  for (const r of results) {
    if (r.winner === 0) u++; else if (r.winner === 1) b++; else d++;
    if (r.timeout) timeouts++;
    t += r.turns;
  }
  return { u, b, d, timeouts, avg: +(t / results.length).toFixed(1) };
}
const fmt = r => `you=${r.u} bot=${r.b} draw=${r.d} timeouts=${r.timeouts} avgTurns=${r.avg}`;

/* ---- Tic-Tac-Toe ---- */
const PERFECT = ['win', 'block', 'fork', 'block-fork', 'center', 'opp-corner', 'corner', 'edge'];

let r = run('tictactoe', PERFECT, PERFECT, 400);
check('TTT perfect vs perfect: every game drawn', r.d === 400, fmt(r));

r = run('tictactoe', [], PERFECT, 400);
check('TTT random never beats perfect bot', r.u === 0, fmt(r));

r = run('tictactoe', PERFECT, [], 400);
check('TTT perfect user never loses to random', r.b === 0, fmt(r));
check('TTT perfect user crushes random', r.u > 300, fmt(r));

r = run('tictactoe', ['win', 'block'], ['win'], 400);
check('TTT win+block beats win-only', r.u > r.b, fmt(r));

/* ---- Snakes & Ladders ---- */
r = run('snakes', ['sniper', 'dodge', 'no-bounce', 'ladder', 'far'], [], 1000);
check('S&L smart stack beats random', r.u > r.b, fmt(r));
check('S&L games always finish', r.timeouts === 0 && r.d === 0, fmt(r));

r = run('snakes', ['small'], ['big'], 1000);
check('S&L tortoise loses to speed', r.u < r.b, fmt(r));

/* ---- Mensch ärgere dich nicht ---- */
r = run('maedn', ['home', 'hunt', 'enter', 'dodge', 'front'], [], 200);
check('MÄDN grandmaster stack crushes random', r.u > 140, fmt(r));
check('MÄDN games terminate', r.timeouts === 0, fmt(r));

r = run('maedn', [], [], 200);
check('MÄDN random vs random roughly fair', Math.abs(r.u - r.b) < 60, fmt(r));

r = run('maedn', ['hunt', 'enter', 'front'], ['front'], 200);
check('MÄDN hunter beats sprinter', r.u > r.b, fmt(r));

/* ---- Monopoly ---- */
const MONA = ['set-hunter', 'blocker', 'tycoon', 'builder', 'cushion', 'bargain', 'sit-jail'];
r = run('monopoly', MONA, [], 200);
check('Monopoly mogul beats random', r.u > r.b, fmt(r));
check('Monopoly games terminate', r.timeouts === 0, fmt(r));

r = run('monopoly', ['buy-all', 'builder', 'pay-jail'], [], 200);
check('Monopoly buy-it-all beats random', r.u > r.b, fmt(r));

/* ---- replay determinism & consistency with match results ---- */
const g = SL.getGame('maedn');
const sim = SL.simulateMatch(g, ['front'], ['hunt', 'enter', 'front'], 20, 999);
let consistent = true, deterministic = true;
for (const idx of [0, 5, 13]) {
  const rep1 = SL.replayGame(g, ['front'], ['hunt', 'enter', 'front'], idx, 999);
  const rep2 = SL.replayGame(g, ['front'], ['hunt', 'enter', 'front'], idx, 999);
  if (rep1.winner !== sim.results[idx].winner) consistent = false;
  if (JSON.stringify(rep1.replay.at(-1).state) !== JSON.stringify(rep2.replay.at(-1).state)) deterministic = false;
  if (rep1.replay.length !== sim.results[idx].turns + 1) consistent = false;
}
check('replays reproduce match games exactly', consistent);
check('replays are deterministic', deterministic);

/* ---- every game state survives JSON cloning + captions exist ---- */
for (const id of ['tictactoe', 'snakes', 'maedn', 'monopoly']) {
  const gm = SL.getGame(id);
  const rep = SL.replayGame(gm, gm.rules.map(x => x.id), gm.botPresets.at(-1).ruleIds, 1, 4242);
  const capsOk = rep.replay.slice(1).every(f => typeof f.caption === 'string' && f.caption.length > 0);
  check(`${id}: replay captions present (${rep.replay.length - 1} moves)`, capsOk);
}

console.log(fails ? `\n${fails} check(s) FAILED` : '\nAll checks passed.');
process.exit(fails ? 1 : 0);
