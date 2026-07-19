/* ============ Skin chrome ============
   Shared UI glue for the skins feature: theme application, the rulebook side
   panel + book icon, and the skin switcher. Used by BOTH the gallery page and
   the Catan page. Node-safe: every DOM access is guarded, and the pure
   resolveSkin() is exported for unit testing.
*/
(function () {
  var g = (typeof window !== 'undefined') ? window : global;
  var hasDoc = (typeof document !== 'undefined');

  var STORAGE_KEY = 'strategy-lab-skin';

  /* -------- pure resolution -------- */
  // Precedence: url > stored > server > available[0] > 'original'.
  // Only ids present in `available` are honoured; others fall through.
  function resolveSkin(opts) {
    opts = opts || {};
    var available = Array.isArray(opts.available) ? opts.available : [];
    function ok(id) { return typeof id === 'string' && available.indexOf(id) >= 0; }
    if (ok(opts.url)) { return opts.url; }
    if (ok(opts.stored)) { return opts.stored; }
    if (ok(opts.server)) { return opts.server; }
    return available.length ? available[0] : 'original';
  }

  /* -------- localStorage -------- */
  function storedSkin() {
    try {
      if (typeof localStorage === 'undefined') { return null; }
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) { return null; }
  }

  function setStoredSkin(id) {
    try {
      if (typeof localStorage === 'undefined') { return; }
      localStorage.setItem(STORAGE_KEY, id);
    } catch (e) { /* private mode: ignore */ }
  }

  /* -------- helpers -------- */
  function esc(s) {
    if (s == null) { return ''; }
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* -------- theme -------- */
  function applyTheme(id) {
    if (!hasDoc || !document.body) { return; }
    var cls = document.body.className.split(/\s+/).filter(function (c) {
      return c && c.indexOf('skin-') !== 0;
    });
    cls.push('skin-' + id);
    document.body.className = cls.join(' ');
  }

  /* -------- rulebook panel -------- */
  var _panel = null;
  var _scrim = null;

  function ensurePanel() {
    if (!hasDoc || !document.body) { return; }
    if (_panel && document.body.contains(_panel)) { return; }

    var panel = document.createElement('aside');
    panel.className = 'rulebook-panel';
    panel.setAttribute('hidden', '');
    var close = document.createElement('button');
    close.className = 'rb-close';
    close.setAttribute('aria-label', 'Close');
    close.textContent = 'x';
    var body = document.createElement('div');
    body.className = 'rb-panel-body';
    panel.appendChild(close);
    panel.appendChild(body);

    var scrim = document.createElement('div');
    scrim.className = 'rb-scrim';
    scrim.setAttribute('hidden', '');

    document.body.appendChild(panel);
    document.body.appendChild(scrim);

    close.addEventListener('click', closePanel);
    scrim.addEventListener('click', closePanel);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closePanel(); }
    });

    _panel = panel;
    _scrim = scrim;
  }

  function renderRulebook(rb) {
    rb = rb || {};
    var steps = Array.isArray(rb.steps) ? rb.steps : [];
    var additional = Array.isArray(rb.additional) ? rb.additional : [];
    var html = '';
    if (rb.summary) {
      html += '<p class="rb-summary">' + esc(rb.summary) + '</p>';
    }
    html += '<ol class="rb-list rb-steps">';
    steps.forEach(function (st) {
      html += '<li>' +
        '<span class="rb-step-title">' + esc(st && st.title) + '</span>' +
        '<span class="rb-step-text">' + esc(st && st.text) + '</span>' +
        '</li>';
    });
    html += '</ol>';
    if (additional.length) {
      html += '<div class="rb-additional">' +
        '<div class="rb-additional-head">Additional rules</div>' +
        '<ul class="rb-list">';
      additional.forEach(function (a) {
        html += '<li>' +
          '<span class="rb-step-title">' + esc(a && a.title) + '</span>' +
          '<span class="rb-step-text">' + esc(a && a.text) + '</span>' +
          '</li>';
      });
      html += '</ul></div>';
    }
    return html;
  }

  function openPanel(rulebook) {
    if (!hasDoc) { return; }
    ensurePanel();
    if (!_panel) { return; }
    var body = _panel.querySelector('.rb-panel-body');
    if (body) { body.innerHTML = renderRulebook(rulebook); }
    // Remove `hidden` first so the transition can run, then add `.open`.
    _panel.removeAttribute('hidden');
    _scrim.removeAttribute('hidden');
    var raf = (typeof requestAnimationFrame !== 'undefined')
      ? requestAnimationFrame
      : function (fn) { setTimeout(fn, 0); };
    raf(function () {
      _panel.classList.add('open');
      _scrim.classList.add('open');
    });
  }

  function closePanel() {
    if (!_panel) { return; }
    _panel.classList.remove('open');
    if (_scrim) { _scrim.classList.remove('open'); }
    _panel.setAttribute('hidden', '');
    if (_scrim) { _scrim.setAttribute('hidden', ''); }
  }

  /* -------- book icon -------- */
  function bookSvg() {
    return '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M4 5a2 2 0 0 1 2-2h5v16H6a2 2 0 0 0-2 2z"/>' +
      '<path d="M20 5a2 2 0 0 0-2-2h-5v16h5a2 2 0 0 1 2 2z"/>' +
      '</svg>';
  }

  function attachBookIcon(anchorEl, rulebook) {
    if (!rulebook) { return null; }
    if (!hasDoc || !anchorEl) { return null; }
    var btn = document.createElement('button');
    btn.className = 'book-icon';
    btn.setAttribute('title', 'Rules');
    btn.setAttribute('aria-label', 'Rules');
    btn.innerHTML = bookSvg();
    btn.addEventListener('click', function () { openPanel(rulebook); });
    anchorEl.appendChild(btn);
    return btn;
  }

  /* -------- skin switcher -------- */
  var _switcher = null;

  function mountSwitcher(opts) {
    if (!hasDoc || !document.body) { return; }
    opts = opts || {};
    var available = Array.isArray(opts.available) ? opts.available : [];
    var active = opts.active;
    var onSwitch = (typeof opts.onSwitch === 'function') ? opts.onSwitch : function () {};

    if (_switcher && document.body.contains(_switcher)) {
      _switcher.parentNode.removeChild(_switcher);
    }
    var box = document.createElement('div');
    box.className = 'skin-switcher';
    available.forEach(function (id) {
      var b = document.createElement('button');
      b.className = 'skin-switcher-btn' + (id === active ? ' on' : '');
      b.textContent = id;
      b.setAttribute('data-skin', id);
      b.addEventListener('click', function () {
        if (id !== active) { onSwitch(id); }
      });
      box.appendChild(b);
    });
    document.body.appendChild(box);
    _switcher = box;
    return box;
  }

  /* -------- bootstraps -------- */
  function init(opts) {
    opts = opts || {};
    var config = opts.config || {};
    ensurePanel();
    mountSwitcher({
      active: opts.active,
      available: config.skins || [],
      onSwitch: opts.onSwitch
    });
  }

  var CATAN_RULEBOOK = {
    summary: 'Settlers of Catan: race to 10 victory points by building on the ' +
      'island and trading the resources it produces.',
    steps: [
      { title: 'Goal',
        text: 'Be the first player to reach 10 victory points. Settlements are ' +
          'worth 1 point each and cities are worth 2.' },
      { title: 'Setup',
        text: 'Each player places two settlements and two roads on the board. ' +
          'You collect starting resources from your second settlement.' },
      { title: 'Produce resources',
        text: 'At the start of a turn a player rolls two dice. Every hex whose ' +
          'number matches the roll pays a resource to the settlements and ' +
          'cities touching it.' },
      { title: 'Build',
        text: 'Spend resources to build: a road (brick + lumber), a settlement ' +
          '(brick + lumber + wool + grain), a city (2 grain + 3 ore) upgrading ' +
          'a settlement, or a development card (wool + grain + ore).' },
      { title: 'The robber on a 7',
        text: 'Rolling a 7 produces nothing; anyone holding more than 7 cards ' +
          'discards half. The roller moves the robber to a hex and steals one ' +
          'card from a player touching it.' },
      { title: 'Trade',
        text: 'On your turn you may trade resources with other players, or with ' +
          'the bank at 4:1 (better at harbors) to get the cards you need.' }
    ],
    additional: [
      { title: 'Longest Road',
        text: 'The first player to build a continuous road of length 5 takes the ' +
          'Longest Road card, worth 2 victory points, until someone builds longer.' },
      { title: 'Largest Army',
        text: 'The first player to play 3 knight development cards takes the ' +
          'Largest Army card, worth 2 victory points, until someone plays more.' }
    ]
  };

  function initCatan() {
    if (!hasDoc) { return; }
    var fallback = { skin: 'original', skins: ['original', 'minimal'] };
    var pfetch = (typeof fetch !== 'undefined')
      ? fetch('/api/config').then(function (r) { return r.json(); }).catch(function () { return fallback; })
      : Promise.resolve(fallback);

    pfetch.then(function (cfg) {
      cfg = cfg || fallback;
      var skins = Array.isArray(cfg.skins) ? cfg.skins : fallback.skins;
      var params = new URLSearchParams(location.search);
      var active = resolveSkin({
        url: params.get('skin'),
        stored: storedSkin(),
        server: cfg.skin,
        available: skins
      });
      applyTheme(active);
      ensurePanel();
      mountSwitcher({
        active: active,
        available: skins,
        onSwitch: function (id) { setStoredSkin(id); location.reload(); }
      });
      var clTop = document.querySelector('.cl-top') || document.body;
      if (clTop.classList) { clTop.classList.add('rb-anchor'); }
      attachBookIcon(clTop, CATAN_RULEBOOK);
    });
  }

  g.SkinChrome = {
    STORAGE_KEY: STORAGE_KEY,
    resolveSkin: resolveSkin,
    storedSkin: storedSkin,
    setStoredSkin: setStoredSkin,
    applyTheme: applyTheme,
    ensurePanel: ensurePanel,
    openPanel: openPanel,
    closePanel: closePanel,
    attachBookIcon: attachBookIcon,
    mountSwitcher: mountSwitcher,
    init: init,
    initCatan: initCatan,
    CATAN_RULEBOOK: CATAN_RULEBOOK
  };

  if (typeof module !== 'undefined') { module.exports = g.SkinChrome; }
})();
