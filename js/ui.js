/* ============================================================
 * Strategy Lab -- thin UI bootstrap.
 *
 * The gallery views themselves now live in skins (js/skins/*.js);
 * this file only:
 *   - owns the persistence store (stacks/bots/beaten/opened) and
 *     the COMING_SOON cards,
 *   - builds the frozen `ctx` handed to every skin,
 *   - resolves + applies the active skin and drives switching.
 *
 * Store ownership: persistence used to live inside js/ui.js's big
 * IIFE; it stays here (the thin bootstrap owns it) and is exposed
 * to skins through ctx.store so every skin shares one store.
 * ============================================================ */
window.UI = (function () {
  'use strict';

  const STORE_KEY = 'strategy-lab-v1';

  // The two locked "coming soon" gallery cards. Moved out of the
  // old ui.js body; exposed to skins via ctx.data.comingSoon.
  const COMING_SOON = [
    { icon: '🛞', name: 'The Game of Life', blurb: 'Careers, kids and a big spinner of destiny.', genre: 'classic' },
    { icon: '🎲', name: 'Backgammon', blurb: 'The oldest race game in the world.', genre: 'board' },
  ];

  /* ---------- persistence store ---------- */
  let stacks = {};   // gameId -> [ruleId]
  let bots = {};     // gameId -> presetId
  let beaten = {};   // gameId -> { presetId: true }
  let opened = {};   // gameId -> true once its explore page has been opened

  function loadStore() {
    try {
      const d = JSON.parse(localStorage.getItem(STORE_KEY)) || {};
      stacks = d.stacks || {};
      bots = d.bots || {};
      beaten = d.beaten || {};
      opened = d.opened || {};
    } catch (e) { stacks = {}; bots = {}; beaten = {}; opened = {}; }
  }
  function saveStore() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ stacks, bots, beaten, opened }));
    } catch (e) { /* private mode etc. -- non-fatal */ }
  }

  /* ---------- active skin + ctx ---------- */
  let activeId = 'original';
  let ctx = null;

  function buildCtx() {
    return {
      root: () => document.getElementById('app'),
      esc: MDP.esc,
      data: {
        StrategyLab: window.StrategyLab,
        MDP: window.MDP,
        genres: window.MDP.genres,
        comingSoon: COMING_SOON,
      },
      play: { EnvPlay: window.EnvPlay, Play: window.Play },
      store: {
        userIdsFor(g) { return stacks[g.id] || (stacks[g.id] = []); },
        presetFor(g) {
          const id = bots[g.id];
          return g.botPresets.find(p => p.id === id) || g.botPresets[0];
        },
        stacks, bots, beaten, opened,
        save() { saveStore(); },
      },
      chrome: window.SkinChrome,
      nav: {
        // A skin need only implement renderHome + openGame; the original
        // skin adds explore/lab. Fall back to the home view so a skin that
        // omits a dispatcher can never crash navigation.
        home() { Skins.get(activeId).renderHome(ctx); },
        openGame(entry) { const s = Skins.get(activeId); if (s.openGame) s.openGame(entry, ctx); else s.renderHome(ctx); },
        explore(entry) { const s = Skins.get(activeId); if (s.explore) s.explore(entry, ctx); else s.renderHome(ctx); },
        lab(game) { const s = Skins.get(activeId); if (s.lab) s.lab(game, ctx); else s.renderHome(ctx); },
      },
    };
  }

  /* ============================= BOOT ============================= */
  function init() {
    loadStore();
    ctx = buildCtx();

    const fallback = { skin: 'original', skins: Skins.list().map(s => s.id) };
    const pfetch = (typeof fetch !== 'undefined')
      ? fetch('/api/config').then(r => r.json()).catch(() => fallback)
      : Promise.resolve(fallback);

    pfetch.then(cfg => {
      cfg = cfg || fallback;
      // Only consider skins the client actually registered, so a server
      // that advertises a skin whose JS is not loaded cannot break boot.
      let skins = (Array.isArray(cfg.skins) && cfg.skins.length ? cfg.skins : fallback.skins)
        .filter(id => Skins.has(id));
      if (!skins.length) skins = Skins.list().map(s => s.id);

      const active = SkinChrome.resolveSkin({
        url: new URLSearchParams(location.search).get('skin'),
        stored: SkinChrome.storedSkin(),
        server: cfg.skin,
        available: skins,
      });
      activeId = active;
      SkinChrome.applyTheme(active);

      const onSwitch = (id) => {
        if (!Skins.has(id)) return;
        SkinChrome.setStoredSkin(id);
        SkinChrome.applyTheme(id);
        activeId = id;
        SkinChrome.mountSwitcher({ active: id, available: skins, onSwitch });
        Skins.get(id).renderHome(ctx);
      };

      SkinChrome.init({ config: { skins }, active, onSwitch });
      Skins.get(active).renderHome(ctx);
    });
  }

  return { init };
})();
