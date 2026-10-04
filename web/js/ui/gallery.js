/* The gallery: a map of chapters -> families -> games.
 *
 * Chapters are the learning path; families are the inheritance groups
 * (games that share a base class); tiles show lock state and stars. */

import { h, local } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { go } from '../router.js';
import { tutorial } from './tutorial.js';

export class GalleryPage {
  async mount(el) {
    this.el = el;
    this.offs = [store.on('catalog', () => this.draw())];
    this.draw();
    tutorial.gallery(this);
  }

  unmount() { this.offs.forEach((f) => f()); }

  draw() {
    const el = this.el;
    el.replaceChildren();
    const cat = store.catalog;
    const name = store.profile.name;
    const next = store.nextGame();
    const prog = store.progress;
    const chapters = cat.chapters.filter((c) => c.id !== 'workbench' || c.count || Object.keys(cat.broken || {}).length);
    const totalGames = chapters.filter((c) => c.id !== 'workbench').reduce((a, c) => a + c.count, 0);

    const hero = h('section.hero',
      h('div.hero-text',
        h('div.hero-kicker.upper', name ? `Welcome back, ${name}` : 'Strategy Lab'),
        h('h1', 'Every game hides a best strategy.', h('br'), h('span.accent-text', 'Find it.')),
        h('p.hero-sub', 'Play a game. Look at it through lenses: odds, game trees, equilibria, learning curves. '
          + 'Then write down the strategy that wins.'),
        h('div.row.wrap.hero-actions',
          next ? h('button.btn.primary.big', { onclick: () => go(`/game/${next.id}`), 'data-tour': 'continue' },
            icon('play'), next.finished ? `Play ${next.name}` : (prog.finished.length ? `Continue: ${next.name}` : `Start with ${next.name}`)) : null,
          h('a.btn.big', { href: '#/history' }, icon('history'), 'Your history'))),
      h('div.hero-art', heroArt()),
      h('div.hero-stats', { 'data-tour': 'progress' },
        stat(prog.finished.length, `of ${totalGames} games finished`),
        stat(Object.values(prog.stars).reduce((a, s) => a + s.length, 0), 'stars earned'),
        stat(prog.concepts.length, 'concept cards')));
    el.append(h('div.page.gallery', hero, h('div.chapters', chapters.map((ch, i) => this.chapter(ch, i)))));
  }

  chapter(ch, index) {
    const open = ch.open;
    const prevTitle = store.catalog.chapters[index - 1]?.title;
    const sec = h('section.chapter', {
      class: `${open ? 'open' : 'locked'} c-${ch.color}`,
      style: { '--cc': `var(--c-${ch.color})` },
      dataset: { chapter: ch.id },
    });
    sec.append(h('header.chapter-head',
      h('div.chapter-badge', icon(ch.icon)),
      h('div.chapter-titles',
        h('div.upper.chapter-num', ch.id === 'workbench' ? 'Workbench' : `Chapter ${index + 1}`),
        h('h2', ch.title, h('span.chapter-sub', ` \u{B7} ${ch.subtitle}`)),
        h('p.chapter-q', ch.question)),
      h('div.chapter-progress', ring(ch.finished, ch.count), h('span.small.muted', `${ch.finished}/${ch.count}`))));
    if (!open) {
      sec.append(h('div.chapter-lock', icon('lock'),
        h('span', `Finish two games in ${prevTitle} to open this chapter.`)));
    } else {
      sec.append(h('p.chapter-intro', ch.intro));
    }
    const fams = h('div.families');
    for (const fam of ch.families) fams.append(this.family(fam, ch));
    if (ch.id === 'workbench') fams.append(...this.broken());
    sec.append(fams);
    return sec;
  }

  family(fam, ch) {
    const showClass = fam.base && fam.base !== 'Game';
    const games = [...fam.games].sort((a, b) => a.order - b.order);
    return h('div.family',
      h('div.family-head',
        h('span.family-name', fam.name),
        showClass ? h('code.family-class', { title: 'Every game here inherits from this class' }, `class ${fam.base}`) : null,
        fam.blurb ? h('span.family-blurb.small.muted', fam.blurb) : null),
      h('div.tiles', games.map((g) => this.tile(g, ch))));
  }

  tile(g, ch) {
    const saved = local.get(`lab.session.v1.${g.id}`, null);
    const inProgress = saved && saved.log?.length && !saved.terminal;
    const state = !g.unlocked ? 'locked' : g.finished ? 'done' : 'new';
    const prev = this.previousIn(ch, g);
    const tile = h('button.tile', {
      class: `state-${state}${g.draft ? ' draft' : ''}`,
      dataset: { game: g.id },
      onclick: () => (g.unlocked ? go(`/game/${g.id}`) : null),
      title: g.unlocked ? g.tagline : (ch.open && prev ? `Finish ${prev.name} to unlock` : 'Locked'),
    },
    h('div.tile-icon', icon(g.icon)),
    h('div.tile-body',
      h('div.tile-name', g.name),
      h('div.tile-tag.small', g.unlocked ? g.tagline : (ch.open && prev ? `Finish ${prev.name} to unlock.` : 'Locked')),
      h('div.tile-foot',
        starRow(g.stars, g.maxStars),
        inProgress ? h('span.chip.tiny.on', 'in progress') : null,
        state === 'new' ? h('span.chip.tiny.new', 'new') : null,
        g.draft ? h('span.chip.tiny', 'draft') : null)),
    !g.unlocked ? h('div.tile-lock', icon('lock')) : null);
    return tile;
  }

  previousIn(ch, g) {
    const all = ch.families.flatMap((f) => f.games).sort((a, b) => a.order - b.order);
    const i = all.findIndex((x) => x.id === g.id);
    return i > 0 ? all[i - 1] : null;
  }

  broken() {
    return Object.entries(store.catalog.broken || {}).map(([mod, tb]) =>
      h('details.broken', h('summary', icon('wrench'), ` ${mod} failed to load`), h('pre', tb)));
  }
}

function stat(n, label) {
  return h('div.hero-stat', h('span.hero-stat-n.num', String(n)), h('span.small.muted', label));
}

export function starRow(n, max) {
  if (!max) return null;
  return h('span.stars', Array.from({ length: max }, (_, i) => icon('star', { cls: i < n ? '' : 'off' })));
}

function ring(done, total) {
  const r = 15;
  const c = 2 * Math.PI * r;
  const frac = total ? done / total : 0;
  return h('span.ring', { html: `<svg viewBox="0 0 36 36" width="36" height="36">
    <circle cx="18" cy="18" r="${r}" fill="none" stroke="var(--line)" stroke-width="4"/>
    <circle cx="18" cy="18" r="${r}" fill="none" stroke="var(--cc)" stroke-width="4" stroke-linecap="round"
      stroke-dasharray="${(frac * c).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 18 18)"/></svg>` });
}

/* A small animated game tree: the lab's logo idea, grown. */
function heroArt() {
  const nodes = [[160, 30], [90, 95], [230, 95], [50, 160], [130, 160], [195, 160], [270, 160]];
  const edges = [[0, 1], [0, 2], [1, 3], [1, 4], [2, 5], [2, 6]];
  const colors = ['var(--c-amber)', 'var(--p0)', 'var(--p1)', 'var(--c-teal)', 'var(--c-violet)', 'var(--c-lime)', 'var(--c-orange)'];
  const labels = ['', '+1', '0', 'W', 'D', 'L', 'W'];
  let s = '<svg viewBox="0 0 320 200" class="tree-art" aria-hidden="true">';
  edges.forEach(([a, b], i) => {
    s += `<line x1="${nodes[a][0]}" y1="${nodes[a][1]}" x2="${nodes[b][0]}" y2="${nodes[b][1]}" style="animation-delay:${i * 120}ms"/>`;
  });
  nodes.forEach(([x, y], i) => {
    s += `<g style="animation-delay:${300 + i * 90}ms"><circle cx="${x}" cy="${y}" r="${i ? 15 : 19}" fill="${colors[i]}"/>`
      + (labels[i] ? `<text x="${x}" y="${y + 4}" text-anchor="middle">${labels[i]}</text>` : '') + '</g>';
  });
  s += '</svg>';
  return h('div', { html: s });
}
