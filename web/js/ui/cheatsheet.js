/* The cheatsheet: every concept card, grouped by chapter. Learned cards
 * open fully; locked ones say which game teaches them. Reachable from the
 * top bar, the game page and with the key "c". */

import { h, local } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { go } from '../router.js';
import { md, math, whenKatex } from '../text.js';
import { closeDrawer, drawer } from './shell.js';

export async function openCheatsheet(focusId = null) {
  const data = await store.loadConcepts(true);
  await whenKatex();
  let showAll = local.get('lab.cs.all', false) || Boolean(store.setting('unlockAll'));
  let query = '';
  let chapter = null;
  const learnedCount = data.concepts.filter((c) => c.learned).length;
  const list = h('div.cs-list');
  const search = h('input.cs-search', { type: 'search', placeholder: 'Search concepts...', oninput: (e) => { query = e.target.value.toLowerCase(); draw(); } });
  const chips = h('div.row.wrap.cs-chapters');
  const chapters = data.chapters.filter((c) => data.concepts.some((x) => x.chapter === c.id));
  const drawChips = () => {
    chips.replaceChildren(
      h('button.chip', { class: chapter == null ? 'on' : '', onclick: () => { chapter = null; drawChips(); draw(); } }, 'All'),
      ...chapters.map((c) => h('button.chip', { class: chapter === c.id ? 'on' : '', style: { '--cc': `var(--c-${c.color})` },
        onclick: () => { chapter = c.id; drawChips(); draw(); } }, icon(c.icon), c.title)));
  };
  const toggle = h('label.toggle.small', h('input', { type: 'checkbox', checked: showAll, onchange: (e) => { showAll = e.target.checked; local.set('lab.cs.all', showAll); draw(); } }), 'Show locked cards');

  function draw() {
    list.replaceChildren();
    for (const ch of chapters) {
      if (chapter && ch.id !== chapter) continue;
      const cards = data.concepts.filter((c) => c.chapter === ch.id && matches(c, query));
      if (!cards.length) continue;
      list.append(h('h3.cs-chapter', { style: { '--cc': `var(--c-${ch.color})` } }, icon(ch.icon), ch.title));
      for (const c of cards) list.append(card(c, showAll, c.id === focusId));
    }
    if (!list.children.length) list.append(h('div.empty', 'No concept matches.'));
  }

  drawChips();
  draw();
  const { panel } = drawer(h('div.cheatsheet',
    h('header.cs-head', h('div', h('h2', icon('cheatsheet'), 'Cheatsheet'),
      h('p.small.muted', `${learnedCount} of ${data.concepts.length} concept cards learned. Finish games to collect more.`)),
    h('button.btn.ghost.icon-only', { onclick: () => closeDrawer(), 'aria-label': 'Close' }, icon('close'))),
    h('div.cs-tools', search, toggle), chips, list));
  if (focusId) {
    const el = panel.querySelector(`[data-concept="${focusId}"]`);
    if (el) setTimeout(() => el.scrollIntoView({ block: 'center', behavior: 'smooth' }), 120);
  }
}

function matches(c, q) {
  if (!q) return true;
  return `${c.title} ${c.short} ${c.body}`.toLowerCase().includes(q);
}

function gameName(id) { return store.gameMeta(id)?.name || id; }

function card(c, showAll, focus) {
  const open = c.learned || showAll;
  const el = h('details.cs-card', { class: `${c.learned ? 'learned' : 'locked'}${focus ? ' focus' : ''}`, open: focus, dataset: { concept: c.id } },
    h('summary', h('span.cs-title', c.learned ? icon('badge') : icon('lock'), c.title), h('span.cs-short', c.short)));
  if (!open) {
    el.append(h('p.small.muted', c.games.length ? ['Learn it by finishing ', joinGames(c.games), '.'] : 'Learn it in a coming game.'));
    return el;
  }
  if (c.formula) el.append(math(c.formula));
  if (c.body) el.append(md(c.body));
  if (c.example) el.append(h('div.cs-example', h('span.upper.muted', 'Example'), md(c.example)));
  const foot = h('div.row.wrap.cs-foot');
  for (const g of c.games) {
    const meta = store.gameMeta(g);
    foot.append(h('button.chip', { disabled: meta && !meta.unlocked, onclick: () => { closeDrawer(); go(`/game/${g}`); } }, icon(meta?.icon || 'puzzle'), gameName(g)));
  }
  for (const r of c.related || []) {
    foot.append(h('button.chip.related', { onclick: () => openCheatsheet(r) }, icon('arrow-right'), r.replace(/-/g, ' ')));
  }
  if (foot.children.length) el.append(foot);
  return el;
}

function joinGames(ids) {
  return ids.map((g, i) => [i ? (i === ids.length - 1 ? ' or ' : ', ') : '', h('strong', gameName(g))]);
}
