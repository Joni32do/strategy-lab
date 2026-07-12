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

/* ---- Play mode: symmetry + decision trace ---- */
require('../js/play.js');   // needs StrategyLab + games already loaded
const Play = window.Play;

const isPerm = p => Array.isArray(p) && p.length === 9 &&
  [...p].sort((a, b) => a - b).every((v, i) => v === i);
check('Play: D4 has 8 transforms, each a permutation of 0..8',
  Play.D4.length === 8 && Play.D4.every(isPerm), `n=${Play.D4.length}`);

const classKey = cls => cls.map(c => [...c.cells].sort((a, b) => a - b).join(',')).sort().join(' | ');
const opening = Play.openingClasses();
check('Play: opening folds 9 squares into 3 classes', opening.length === 3, `n=${opening.length}`);
check('Play: opening classes are center / corners / edges',
  classKey(opening) === '0,2,6,8 | 1,3,5,7 | 4', classKey(opening));

const EMPTY = Array(9).fill(null);
check('Play: empty board keeps all 8 symmetries', Play.stabilizers(EMPTY).length === 8);

const centerOnly = [...EMPTY]; centerOnly[4] = 0;
const centerReplies = Play.moveClasses(centerOnly, [0, 1, 2, 3, 5, 6, 7, 8]);
check('Play: center-only board keeps all 8 symmetries', Play.stabilizers(centerOnly).length === 8);
check('Play: 8 replies to a center opening fold to 2 classes',
  centerReplies.length === 2, classKey(centerReplies));

const cornerOnly = [...EMPTY]; cornerOnly[0] = 0;
const cornerReplies = Play.moveClasses(cornerOnly, [1, 2, 3, 4, 5, 6, 7, 8]);
check('Play: 8 replies to a corner opening fold to 5 classes',
  cornerReplies.length === 5, classKey(cornerReplies));

const asym = [...EMPTY]; asym[0] = 0; asym[1] = 1;
const asymReplies = Play.moveClasses(asym, [2, 3, 4, 5, 6, 7, 8]);
check('Play: asymmetric board folds nothing (7 cells, 7 classes)',
  asymReplies.length === 7, classKey(asymReplies));

const ttt = SL.getGame('tictactoe');
// X holds 0,1 (can win at 2); O holds 3,4 (threatens 5); X to move.
const nearWin = { board: [0, 0, null, 1, 1, null, null, null, null], current: 0, marks: ['X', 'O'] };
let tr = Play.traceDecision(ttt, nearWin, ['win', 'block', 'center'], 0);
check('Play: trace picks the win card and completes the row',
  !!tr.rule && tr.rule.id === 'win' && tr.move === 2, `rule=${tr.rule && tr.rule.id} move=${tr.move}`);
tr = Play.traceDecision(ttt, nearWin, ['block'], 0);
check('Play: block-only stack blocks at square 5', tr.move === 5, `move=${tr.move}`);
tr = Play.traceDecision(ttt, nearWin, [], 0);
check('Play: empty stack falls through to random', tr.random === true && tr.move === null);

const fresh = { board: [...EMPTY], current: 0, marks: ['X', 'O'] };
const tc1 = Play.traceDecision(ttt, fresh, ['corner'], 0);   // corner card draws on an rng
const tc2 = Play.traceDecision(ttt, fresh, ['corner'], 0);
check('Play: trace is pure - repeated calls agree (rng-using card)',
  tc1.move === tc2.move && tc1.move !== null, `move=${tc1.move}`);
const tp1 = Play.traceDecision(ttt, nearWin, PERFECT, 0);
const tp2 = Play.traceDecision(ttt, nearWin, PERFECT, 0);
check('Play: trace is pure - repeated calls agree (perfect stack)',
  tp1.move === tp2.move && tp1.move === 2, `move=${tp1.move}`);

const pgStacks = [SL.resolveStack(ttt, PERFECT), SL.resolveStack(ttt, [])];
const pg1 = SL.playGame(ttt, pgStacks, 0, 42, false);
const pg2 = SL.playGame(ttt, pgStacks, 0, 42, false);
check('playGame: perfect vs empty from seed 42 is deterministic',
  pg1.winner === pg2.winner && pg1.turns === pg2.turns,
  `winner=${pg1.winner} turns=${pg1.turns}`);
const cm = SL.chooseMove(ttt, nearWin, SL.resolveStack(ttt, PERFECT), 0, SL.mulberry32(1));
check('chooseMove: perfect stack takes the winning square', cm === 2, `move=${cm}`);

console.log(fails ? `\n${fails} check(s) FAILED` : '\nAll checks passed.');
process.exit(fails ? 1 : 0);
