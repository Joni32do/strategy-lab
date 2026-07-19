/* ============ Minimal skin ============
   The lean antidote to the text-heavy original: no hero, no blurbs, no
   cards/chips/icons-as-art. Home is just game NAMES grouped under their
   GENRE headings. Clicking a name opens a BARE play view -- the game's
   action space and nothing else.

   Registers itself into window.Skins (see js/skins/registry.js). Every
   DOM access lives inside functions invoked at render time, never at
   module load, so this file can be `require`d under a DOM-free shim.
*/
(function () {
  var g = (typeof window !== 'undefined') ? window : global;

  /* -------- home: build genre -> [{kind,id,label,blurb}] buckets -------- */
  function buildGenres(ctx) {
    var genres = (ctx.data && ctx.data.genres) || [];
    var buckets = {};
    genres.forEach(function (gr) { buckets[gr.id] = []; });

    function pushTo(genreId, item) {
      if (!buckets[genreId]) { buckets[genreId] = []; }
      buckets[genreId].push(item);
    }

    var slGames = (ctx.data && ctx.data.StrategyLab && ctx.data.StrategyLab.games) || [];
    slGames.forEach(function (game) {
      pushTo('classic', { kind: 'card', id: game.id, label: game.name });
    });

    // Catan: hardcoded -- it lives outside MDP.games, reached via catan.html.
    pushTo('board', { kind: 'catan', id: 'catan', label: 'Settlers of Catan' });

    var mdpGames = (ctx.data && ctx.data.MDP && ctx.data.MDP.games) || [];
    mdpGames.forEach(function (entry) {
      if (entry.playable) { return; } // already shown as a card-stack game above
      pushTo(entry.genre, { kind: 'mdp', id: entry.id, label: entry.name });
    });

    var soon = (ctx.data && ctx.data.comingSoon) || [];
    soon.forEach(function (item) {
      pushTo(item.genre, {
        kind: 'soon', id: null, label: item.name, blurb: item.blurb
      });
    });

    return genres
      .map(function (gr) { return { id: gr.id, name: gr.name, items: buckets[gr.id] || [] }; })
      .filter(function (gr) { return gr.items.length > 0; });
  }

  function itemHTML(esc, it) {
    if (it.kind === 'soon') {
      return '<li><button class="min-name soon" data-kind="soon" disabled' +
        (it.blurb ? ' title="' + esc(it.blurb) + '"' : '') + '>' +
        esc(it.label) + '</button></li>';
    }
    return '<li><button class="min-name" data-kind="' + esc(it.kind) + '" data-id="' +
      esc(it.id) + '">' + esc(it.label) + '</button></li>';
  }

  function renderHome(ctx) {
    // Stop any live env session (gym random-policy / spiel autoplay
    // loops keep stepping + fetching otherwise); mirrors the original
    // skin's showHome. Covers Back from a play shell AND switching
    // skins away from a view that mounted EnvPlay.
    if (ctx.play && ctx.play.EnvPlay) { ctx.play.EnvPlay.unmount(); }
    var esc = ctx.esc;
    var groups = buildGenres(ctx);

    var html = '<div class="min-home">' +
      '<h1 class="min-title">Strategy Lab</h1>';
    groups.forEach(function (gr) {
      html += '<section class="min-genre" data-genre="' + esc(gr.id) + '">' +
        '<h2>' + esc(gr.name) + '</h2>' +
        '<ul class="min-list">' +
        gr.items.map(function (it) { return itemHTML(esc, it); }).join('') +
        '</ul></section>';
    });
    html += '</div>';

    ctx.root().innerHTML = html;

    var homeEl = ctx.root().querySelector('.min-home');
    if (!homeEl) { return; }
    homeEl.addEventListener('click', function (e) {
      var btn = e.target.closest('button.min-name[data-kind]');
      if (!btn || btn.disabled) { return; }
      openGame({ kind: btn.getAttribute('data-kind'), id: btn.getAttribute('data-id') }, ctx);
    });
  }

  /* -------- bare back button, shared by every play/browse view -------- */
  function backButtonHTML() {
    return '<button class="min-back" id="min-back">&lsaquo; Back</button>';
  }

  function wireBack(ctx) {
    var btn = ctx.root().querySelector('#min-back');
    if (btn) { btn.addEventListener('click', ctx.nav.home); }
  }

  /* -------- routing: dispatch a {kind,id} descriptor to a play view -------- */
  function openGame(entry, ctx) {
    if (!entry) { return; }

    if (entry.kind === 'catan') {
      location.href = 'catan.html';
      return;
    }

    if (entry.kind === 'card') {
      var game = ctx.data.StrategyLab.getGame(entry.id);
      if (!game) { return; }
      ctx.play.Play.open(game, ctx.store.userIdsFor(game), ctx.store.presetFor(game),
        { onBack: ctx.nav.home });
      return;
    }

    if (entry.kind === 'mdp') {
      var mdpEntry = ctx.data.MDP.get ? ctx.data.MDP.get(entry.id)
        : (ctx.data.MDP.games || []).find(function (e) { return e.id === entry.id; });
      if (!mdpEntry) { return; }
      if (mdpEntry.play) { openPlayShell(mdpEntry, ctx); }
      else { openBrowseOnly(mdpEntry, ctx); }
      return;
    }
  }

  /* Bare shell for a live MDP entry (gym or spiel backend). The outer
   * .play-canvas section is the stable anchor for the book icon; the
   * inner #play-host div is what EnvPlay.mount rewrites (innerHTML) on
   * every move, so the icon must NOT live inside it or it gets wiped. */
  function openPlayShell(entry, ctx) {
    ctx.root().innerHTML = backButtonHTML() +
      '<section class="panel play-canvas" id="min-play-canvas">' +
      '<div id="play-host"></div>' +
      '</section>';
    wireBack(ctx);

    var playCanvas = ctx.root().querySelector('#min-play-canvas');
    var host = ctx.root().querySelector('#play-host');
    ctx.play.EnvPlay.mount(entry, host);
    if (entry.rulebook && playCanvas) {
      ctx.chrome.attachBookIcon(playCanvas, entry.rulebook);
    }
  }

  /* Browse-only stub for an MDP entry with no live backend wired. */
  function openBrowseOnly(entry, ctx) {
    var esc = ctx.esc;
    ctx.root().innerHTML = backButtonHTML() +
      '<section class="panel min-browse">' +
      '<h2>' + esc(entry.name) + '</h2>' +
      (entry.blurb ? '<p>' + esc(entry.blurb) + '</p>' : '') +
      '<p class="muted">Browse only - no live engine wired.</p>' +
      '</section>';
    wireBack(ctx);
  }

  g.Skins.register({
    id: 'minimal',
    name: 'Minimal',
    renderHome: renderHome,
    openGame: openGame
  });

  if (typeof module !== 'undefined') { module.exports = { renderHome: renderHome, openGame: openGame }; }
})();
