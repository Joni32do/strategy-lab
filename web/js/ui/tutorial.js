/* The tutorial: an intro of four slides on the first visit, then short
 * coach marks that point at one thing at a time (gallery, then the first
 * game page). Progress lives in profile.tutorial; "Replay the tutorial" in
 * the settings resets it. */

import { api } from '../api.js';
import { h } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { go } from '../router.js';
import { closeModal, modal } from './shell.js';

/* ------------------------------------------------------------------ intro */
const SLIDES = [
  {
    kicker: 'Welcome',
    title: 'Every game hides a best strategy.',
    body: 'Some are known: perfect Tic-Tac-Toe is always a draw. Some games are mostly luck in '
      + 'disguise. Some strategies have to be learned. In the lab you play a game, then look '
      + 'at it through lenses until you see how to win.',
    art: 'tree',
  },
  {
    kicker: 'How it works',
    title: 'Play. Look. Write it down. Learn.',
    steps: [
      ['gamepad', 'Play', 'Against bots with personalities, from Randy Rookie to perfect.'],
      ['eye', 'Look', 'Lenses show odds, game trees, equilibria and learning curves.'],
      ['cards', 'Write it down', 'Turn what you saw into rule cards and test them on 100 games.'],
      ['cheatsheet', 'Learn', 'Every idea lands on your cheatsheet as a concept card.'],
    ],
  },
  {
    kicker: 'Your path',
    title: 'Seven chapters, one idea each.',
    chapters: true,
    body: 'Chapters open as you play. Inside a chapter, games come one after another. '
      + 'Explorer mode in the settings opens everything at once.',
  },
  {
    kicker: 'Your first concept card',
    title: 'Policy',
    card: {
      title: 'Policy',
      short: 'A policy is a complete strategy: for every situation, what you would do.',
      body: 'Finding a good policy is what this whole lab is about. Rule cards, game trees, '
        + 'equilibria and learning are four ways to write one down.',
    },
    name: true,
  },
];

let running = false;

async function intro(force = false) {
  if (running) return;
  if (!force && store.profile.tutorial.intro) return;
  running = true;
  if (force) await store.patch({ tutorial: { intro: false, done: [], skipped: false } });
  let i = 0;
  let name = store.profile.name || '';
  const finish = async () => {
    closeModal();
    running = false;
    await store.patch({ name: name.trim(), tutorial: { intro: true } });
    const r = await api.seeConcept('policy');
    await store.achieved(r.achieved);
    const next = store.nextGame();
    if (next) go(`/game/${next.id}`);
  };
  const draw = () => {
    const s = SLIDES[i];
    const body = h('div.slide');
    body.append(h('div.upper.slide-kicker', s.kicker), h('h1', s.title));
    if (s.art === 'tree') body.append(h('div.slide-art', { html: treeArt() }));
    if (s.body && !s.card) body.append(h('p.slide-body', s.body));
    if (s.steps) {
      body.append(h('div.slide-steps', s.steps.map(([ic, t, x], k) =>
        h('div.slide-step', { style: { animationDelay: `${k * 90}ms` } }, h('span.slide-step-icon', icon(ic)), h('strong', t), h('span.small.muted', x)))));
    }
    if (s.chapters) {
      const chs = (store.catalog?.chapters || []).filter((c) => c.id !== 'workbench');
      body.append(h('ol.slide-chapters', chs.map((c, k) => h('li', { style: { '--cc': `var(--c-${c.color})`, animationDelay: `${k * 70}ms` } },
        h('span.chapter-badge.small', icon(c.icon)), h('span', h('strong', c.title), h('span.small.muted', ` ${c.question}`))))));
      body.append(h('p.slide-body', s.body));
    }
    if (s.card) {
      body.append(h('div.concept-preview', h('div.upper.muted', 'Concept card'), h('h3', s.card.title), h('p', h('strong', s.card.short)), h('p.small.muted', s.card.body)));
      body.append(h('label.field.name-field', h('span', 'What should the lab call you? (optional)'),
        h('input', { type: 'text', value: name, maxlength: 40, placeholder: 'Your name', oninput: (e) => { name = e.target.value; } })));
    }
    const dots = h('div.dots', SLIDES.map((_, k) => h('span', { class: k === i ? 'on' : '' })));
    const last = i === SLIDES.length - 1;
    body.append(h('div.slide-nav', dots, h('div.row',
      h('button.btn.ghost', { onclick: async () => { closeModal(); running = false; await store.patch({ tutorial: { intro: true, skipped: true } }); } }, 'Skip'),
      i > 0 ? h('button.btn', { onclick: () => { i -= 1; draw(); } }, 'Back') : null,
      h('button.btn.primary', { onclick: () => { if (last) finish(); else { i += 1; draw(); } } }, last ? 'Let\'s play' : 'Next', icon('arrow-right')))));
    modal(body, { wide: true, dismissable: false });
  };
  draw();
}

function treeArt() {
  return `<svg viewBox="0 0 360 150" aria-hidden="true">
    <g class="ta-edges">
      <line x1="180" y1="22" x2="90" y2="75"/><line x1="180" y1="22" x2="180" y2="75"/><line x1="180" y1="22" x2="270" y2="75"/>
      <line x1="90" y1="75" x2="50" y2="128"/><line x1="90" y1="75" x2="130" y2="128"/>
      <line x1="270" y1="75" x2="230" y2="128"/><line x1="270" y1="75" x2="310" y2="128"/></g>
    <circle cx="180" cy="22" r="13" fill="var(--c-amber)"/>
    <circle cx="90" cy="75" r="11" fill="var(--p0)"/><circle cx="180" cy="75" r="11" fill="var(--p0)"/><circle cx="270" cy="75" r="11" fill="var(--p0)"/>
    <circle cx="50" cy="128" r="9" fill="var(--good)"/><circle cx="130" cy="128" r="9" fill="var(--muted)"/>
    <circle cx="230" cy="128" r="9" fill="var(--bad)"/><circle cx="310" cy="128" r="9" fill="var(--good)"/>
  </svg>`;
}

/* ------------------------------------------------------------- coach marks */
let tourLayer = null;

function coachSequence(steps) {
  const todo = steps.filter((s) => !store.tutorialDone(s.id));
  if (!todo.length || store.profile.tutorial.skipped || !store.profile.tutorial.intro) return;
  let k = 0;
  const show = () => {
    removeTour();
    while (k < todo.length && !todo[k].target()) k += 1;
    if (k >= todo.length) return;
    const st = todo[k];
    const target = st.target();
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    setTimeout(() => {
      const r = target.getBoundingClientRect();
      const spot = h('div.tour-spot', { style: { top: `${r.top - 6}px`, left: `${r.left - 6}px`, width: `${r.width + 12}px`, height: `${r.height + 12}px` } });
      const below = r.bottom + 220 < innerHeight;
      const bubble = h('div.tour-bubble', {
        style: { top: below ? `${r.bottom + 14}px` : `${Math.max(12, r.top - 14)}px`, left: `${Math.min(Math.max(12, r.left), innerWidth - 340)}px`,
          transform: below ? 'none' : 'translateY(-100%)' },
      },
      h('div.upper.muted', `${k + 1} / ${todo.length}`),
      h('h3', st.title), h('p', st.text),
      h('div.row.between',
        h('button.btn.ghost.small', { onclick: async () => { removeTour(); await store.patch({ tutorial: { skipped: true } }); } }, 'Skip tour'),
        h('button.btn.primary.small', { onclick: async () => { await store.markTutorial(st.id); k += 1; show(); } }, k === todo.length - 1 ? 'Done' : 'Got it')));
      tourLayer = h('div.tour', spot, bubble);
      document.body.append(tourLayer);
    }, 260);
  };
  setTimeout(show, 500);
}

function removeTour() { if (tourLayer) { tourLayer.remove(); tourLayer = null; } }

const $ = (sel) => () => document.querySelector(sel);

export const tutorial = {
  intro,

  gallery() {
    coachSequence([
      { id: 'g-start', target: $('[data-tour="continue"]'), title: 'Start here',
        text: 'The next game on your path. Finish a game once and the one after it opens.' },
      { id: 'g-progress', target: $('[data-tour="progress"]'), title: 'Your progress',
        text: 'Games finished, stars from challenges, and concept cards. The History page keeps every game you play.' },
      { id: 'g-chapters', target: $('.chapter.locked') || $('.chapter:nth-child(2)'), title: 'Chapters and families',
        text: 'Games are grouped by the idea they teach. Inside a chapter, a family is a set of games that share one base class: same rules engine, other numbers.' },
      { id: 'g-cheatsheet', target: $('.cheatsheet-btn'), title: 'Your cheatsheet',
        text: 'Every concept you meet is collected here with a formula and an example. Press C anywhere.' },
    ]);
  },

  game() {
    coachSequence([
      { id: 'p-board', target: $('.board-wrap'), title: 'The board',
        text: 'Click to play. Dice and bots move by themselves; the move log under the board keeps track.' },
      { id: 'p-lenses', target: $('[data-tour="lenses"]'), title: 'Lenses',
        text: 'Each tab shows the game differently: the odds of every outcome, the game tree, equilibria, learning curves. Badges appear right on the board.' },
      { id: 'p-goals', target: $('[data-tab="goals"]'), title: 'Goals',
        text: 'Challenges give stars. Finishing the game adds its concepts to your cheatsheet.' },
      { id: 'p-new', target: $('[data-tour="new-game"]'), title: 'Opponents and variants',
        text: 'Pick another bot or change the rules here. U undoes your last move, N starts a new game.' },
    ]);
  },
};

window.addEventListener('hashchange', removeTour);
