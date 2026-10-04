/* Boot: icons, profile and catalog, skin, shell, routes, tutorial, and the
 * dev-mode live reload (Python edits replay the open game, web edits
 * reload the page). */

import { api } from './api.js';
import { h, local } from './dom.js';
import { loadIcons } from './icons.js';
import { store } from './store.js';
import { route, startRouter } from './router.js';
import { setSkin } from './skins/registry.js';
import { initShell } from './ui/shell.js';
import { GalleryPage } from './ui/gallery.js';
import { GamePage } from './ui/game-page.js';
import { HistoryPage } from './ui/history-page.js';
import { openCheatsheet } from './ui/cheatsheet.js';
import { initCelebrate } from './ui/celebrate.js';
import { tutorial } from './ui/tutorial.js';

async function boot() {
  const root = document.getElementById('app');
  await loadIcons();
  try {
    await store.load();
  } catch (e) {
    root.replaceChildren(h('div.page.narrow', h('h2', 'The lab server is not answering'),
      h('p', 'Start it with:'), h('pre', 'uv run python -m strategy_lab serve --dev'), h('p.muted', e.message)));
    return;
  }
  await store.loadConcepts().catch(() => null);   // titles for concept chips
  let version = null;
  try { version = await api.devVersion(); store.dev = Boolean(version.dev); } catch { /* not fatal */ }
  setSkin(store.profile.settings.skin);
  const outlet = initShell(root, {
    cheatsheet: () => openCheatsheet(),
    tutorial: () => tutorial.intro(true),
    reset: async () => {
      await api.resetProfile();
      for (const k of Object.keys(localStorage)) if (k.startsWith('lab.')) local.remove(k);
      location.hash = '#/';
      location.reload();
    },
  });
  initCelebrate();
  route('/', GalleryPage);
  route('/game/:id', GamePage);
  route('/history', HistoryPage);
  await startRouter(outlet);
  if (!store.profile.tutorial.intro) tutorial.intro();
  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'c') openCheatsheet();
  });
  if (store.dev && version) devReload(version);
}

/* Poll the server; see GET /api/dev/version. */
function devReload(first) {
  let server = first.server;
  let stat = first.static;
  setInterval(async () => {
    let v;
    try { v = await api.devVersion(); } catch { return; }   // restarting: try again
    if (v.static !== stat) { location.reload(); return; }
    if (v.server !== server) {
      server = v.server;
      await store.refresh();
      store.emit('reloaded');
    }
  }, 1200);
}

boot();
