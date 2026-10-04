/* Your history: profile, totals, per-game records and recent games with
 * replays. Everything comes from data/history.jsonl via the API. */

import { api } from '../api.js';
import { h, timeAgo } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { splitBar } from '../charts.js';

export class HistoryPage {
  async mount(el) {
    this.el = el;
    await store.refresh();
    const { games } = await api.history({ limit: 40 });
    this.recent = games;
    this.draw();
  }

  draw() {
    const p = store.profile;
    const st = store.stats;
    const prog = store.progress;
    const stars = Object.values(prog.stars).reduce((a, s) => a + s.length, 0);
    const since = new Date(p.created * 1000).toLocaleDateString();
    const nameInput = h('input.name-input', { value: p.name, placeholder: 'Your name', maxlength: 40,
      onchange: (e) => store.patch({ name: e.target.value.trim() }) });
    const page = h('div.page.history');
    page.append(h('section.profile-card',
      h('div.avatar', (p.name || '?').slice(0, 1).toUpperCase()),
      h('div.grow', nameInput, h('p.small.muted', `In the lab since ${since}`)),
      st.dayStreak > 1 ? h('div.chip.on', icon('flame'), `${st.dayStreak}-day streak`) : null));
    page.append(h('div.tiles-stats',
      tile('gamepad', st.total, 'games played'),
      tile('trophy', st.wins, 'wins'),
      tile('star', stars, 'stars'),
      tile('cheatsheet', prog.concepts.length, 'concept cards'),
      tile('fast', st.sims, 'simulations'),
      tile('eye', st.lenses, 'lenses opened')));

    const chapters = store.catalog.chapters.filter((c) => c.id !== 'workbench');
    page.append(h('h2', 'Your path'), h('div.path-progress', chapters.map((c) =>
      h('div.path-row', { style: { '--cc': `var(--c-${c.color})` }, class: c.open ? '' : 'locked' },
        h('span.chapter-badge.small', icon(c.open ? c.icon : 'lock')),
        h('strong', c.title),
        h('span.path-track', h('span', { style: { width: `${c.count ? (c.finished / c.count) * 100 : 0}%` } })),
        h('span.num.small', `${c.finished}/${c.count}`)))));

    const rows = Object.entries(st.games).sort((a, b) => b[1].last - a[1].last);
    page.append(h('h2', 'By game'));
    if (!rows.length) page.append(h('div.empty', 'No finished games yet. Your first one will show up here.'));
    else {
      page.append(h('div.game-records', rows.map(([gid, r]) => {
        const meta = store.gameMeta(gid) || { name: gid, icon: 'puzzle' };
        return h('div.record', h('span.title-icon', icon(meta.icon)),
          h('div.grow', h('strong', meta.name), h('div.small.muted', `${r.played} played \u{B7} last ${timeAgo(r.last)}${r.best != null ? ` \u{B7} best ${fmt(r.best)}` : ''}`),
            splitBar([{ value: r.win, color: 'var(--good)', label: 'W' }, { value: r.draw, color: 'var(--muted)', label: 'D' }, { value: r.loss, color: 'var(--bad)', label: 'L' }])),
          h('a.btn.small', { href: `#/game/${gid}` }, icon('play'), 'Play'));
      })));
    }

    page.append(h('h2', 'Recent games'));
    if (!this.recent.length) page.append(h('div.empty', 'Nothing yet.'));
    else {
      page.append(h('table.recent', h('tbody', this.recent.map((g) => {
        const meta = store.gameMeta(g.game) || { name: g.game };
        return h('tr', h('td', meta.name), h('td', h(`span.chip.tiny.out-${g.outcome}`, g.outcome)),
          h('td.small.muted', `vs ${(g.bots || []).join(', ') || '-'}`), h('td.small.muted', `${g.steps} steps`),
          h('td.small.muted', timeAgo(g.ts)), h('td', h('a.btn.small.ghost', { href: `#/game/${g.game}?replay=${g.id}` }, icon('history'), 'Replay')));
      }))));
    }
    this.el.replaceChildren(page);
  }
}

function tile(ic, n, label) {
  return h('div.stat-tile', icon(ic), h('span.num.stat-tile-n', String(n ?? 0)), h('span.small.muted', label));
}

function fmt(x) { return Number.isInteger(x) ? String(x) : x.toFixed(1); }
