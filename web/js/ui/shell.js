/* The shell around every page: header, popover menus, modal, drawer and
 * toasts. Pages render into the outlet returned by initShell(). */

import { clear, h } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { SKINS, setSkin, skin } from '../skins/registry.js';

let layers = null;

export function brandMark(size = 30) {
  const s = `<svg viewBox="0 0 32 32" width="${size}" height="${size}" aria-hidden="true">
    <path d="M16 9 L9 21 M16 9 L23 21" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round"/>
    <circle cx="16" cy="8" r="3.4" fill="var(--c-amber)"/>
    <circle cx="9" cy="22.5" r="3.4" fill="var(--p0)"/>
    <circle cx="23" cy="22.5" r="3.4" fill="var(--p1)"/></svg>`;
  return h('span.brand-mark', { html: s });
}

export function initShell(root, handlers) {
  clear(root);
  const header = h('header.topbar');
  const outlet = h('main.outlet');
  layers = {
    modal: h('div.modal-layer'),
    drawer: h('div.drawer-layer'),
    toasts: h('div.toasts'),
    pop: null,
  };
  root.append(header, outlet, layers.drawer, layers.modal, layers.toasts);
  drawHeader(header, handlers);
  store.on('profile', () => drawHeader(header, handlers));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closePop(); closeModal(); closeDrawer(); }
  });
  document.addEventListener('click', (e) => {
    if (layers.pop && !layers.pop.contains(e.target) && !e.target.closest('[data-pop]')) closePop();
  });
  return outlet;
}

function drawHeader(header, handlers) {
  clear(header);
  const prog = store.progress || { finished: [], stars: {}, concepts: [] };
  const total = (store.catalog?.chapters || []).filter((c) => c.id !== 'workbench').reduce((a, c) => a + c.count, 0);
  const stars = Object.values(prog.stars || {}).reduce((a, s) => a + s.length, 0);
  const brand = h('a.brand', { href: '#/' }, brandMark(), h('span.brand-name', 'Strategy Lab'));
  const nav = h('nav.topnav',
    h('a.navlink', { href: '#/' }, icon('map'), h('span', 'Gallery')),
    h('a.navlink', { href: '#/history' }, icon('history'), h('span', 'History')));
  const chips = h('div.progress-chips',
    h('a.chip', { href: '#/history', title: 'Games finished' }, icon('check'), `${prog.finished.length}/${total}`),
    h('a.chip', { href: '#/history', title: 'Stars earned' }, icon('star'), String(stars)),
    h('button.chip', { title: 'Concept cards learned', onclick: () => handlers.cheatsheet() }, icon('cheatsheet'), String(prog.concepts.length)));
  const tools = h('div.tools',
    h('button.btn.ghost.cheatsheet-btn', { onclick: () => handlers.cheatsheet(), title: 'Cheatsheet (c)' }, icon('cheatsheet'), h('span', 'Cheatsheet')),
    h('button.btn.ghost.icon-only', { 'data-pop': 'skin', title: 'Skin', onclick: (e) => skinMenu(e.currentTarget) }, icon('palette')),
    h('button.btn.ghost.icon-only', { 'data-pop': 'settings', title: 'Settings', onclick: (e) => settingsMenu(e.currentTarget, handlers) }, icon('settings')));
  if (store.dev) tools.prepend(h('span.chip.dev-chip', { title: 'Dev mode: edits reload live' }, icon('bolt'), 'dev'));
  header.append(brand, nav, chips, tools);
}

/* ------------------------------------------------------------------ popovers */
export function popover(anchor, content) {
  closePop();
  const r = anchor.getBoundingClientRect();
  const pop = h('div.popover', content);
  pop.style.top = `${r.bottom + 8 + window.scrollY}px`;
  pop.style.right = `${Math.max(12, window.innerWidth - r.right)}px`;
  document.body.append(pop);
  layers.pop = pop;
  return pop;
}

export function closePop() { if (layers?.pop) { layers.pop.remove(); layers.pop = null; } }

function skinMenu(anchor) {
  const cur = skin().id;
  popover(anchor, h('div.menu',
    h('div.menu-title', 'Skin'),
    SKINS.map((S) => h('button.menu-item', { class: S.id === cur ? 'on' : '', onclick: async () => {
      setSkin(S.id);
      closePop();
      await store.patch({ settings: { skin: S.id } });
      store.emit('skin', S.id);
    } }, h('span.swatch', { 'data-skin-swatch': S.id }), h('span', h('strong', S.label), h('span.small.muted', S.blurb))))));
}

function settingsMenu(anchor, handlers) {
  const st = store.profile.settings;
  popover(anchor, h('div.menu',
    h('div.menu-title', 'Settings'),
    h('label.menu-item.toggle', h('input', { type: 'checkbox', checked: st.unlockAll, onchange: async (e) => {
      await store.patch({ settings: { unlockAll: e.target.checked } });
      toast(e.target.checked ? 'Explorer mode: every game is open.' : 'Explorer mode off: games unlock as you play.');
    } }), h('span', h('strong', 'Explorer mode'), h('span.small.muted', 'Open every game now'))),
    h('label.menu-item.toggle', h('input', { type: 'checkbox', checked: st.motion !== false, onchange: (e) => store.patch({ settings: { motion: e.target.checked } }) }),
      h('span', h('strong', 'Animations'), h('span.small.muted', 'Dice rolls, confetti, slides'))),
    h('button.menu-item', { onclick: () => { closePop(); handlers.tutorial(); } }, icon('graduation'), h('span', h('strong', 'Replay the tutorial'))),
    h('button.menu-item.danger', { onclick: async () => {
      closePop();
      if (await confirmBox('Forget your profile, history, stars and concept cards?', 'Reset everything')) handlers.reset();
    } }, icon('reset'), h('span', h('strong', 'Reset progress')))));
}

/* --------------------------------------------------------------------- modal */
let modalClose = null;

export function modal(content, { wide = false, onClose, dismissable = true } = {}) {
  closeModal();
  const box = h('div.modal', { class: wide ? 'wide' : '', role: 'dialog' }, content);
  const scrim = h('div.scrim', { onclick: () => { if (dismissable) closeModal(); } });
  clear(layers.modal).append(scrim, box);
  layers.modal.classList.add('open');
  modalClose = () => {
    layers.modal.classList.remove('open');
    clear(layers.modal);
    modalClose = null;
    if (onClose) onClose();
  };
  return modalClose;
}

export function closeModal() { if (modalClose) modalClose(); }

export function confirmBox(text, okLabel = 'OK') {
  return new Promise((resolve) => {
    const done = (v) => { closeModal(); resolve(v); };
    modal(h('div.confirm', h('p', text), h('div.row.end',
      h('button.btn', { onclick: () => done(false) }, 'Cancel'),
      h('button.btn.primary', { onclick: () => done(true) }, okLabel))));
  });
}

/* -------------------------------------------------------------------- drawer */
let drawerClose = null;

export function drawer(content, { onClose } = {}) {
  closeDrawer();
  const panel = h('aside.drawer', content);
  const scrim = h('div.scrim', { onclick: () => closeDrawer() });
  clear(layers.drawer).append(scrim, panel);
  requestAnimationFrame(() => layers.drawer.classList.add('open'));
  drawerClose = () => {
    layers.drawer.classList.remove('open');
    setTimeout(() => { if (!drawerClose) clear(layers.drawer); }, 300);
    drawerClose = null;
    if (onClose) onClose();
  };
  return { panel, close: drawerClose };
}

export function closeDrawer() { if (drawerClose) drawerClose(); }

/* -------------------------------------------------------------------- toasts */
export function toast(content, { tone = 'info', timeout = 4200, icon: ic = null, actions = [] } = {}) {
  const el = h('div.toast', { class: `tone-${tone}` },
    ic ? h('span.toast-icon', icon(ic)) : null,
    h('div.toast-body', content),
    actions.length ? h('div.toast-actions', actions.map((a) => h('button.btn.small', {
      onclick: () => { a.onclick(); dismiss(); },
    }, a.label))) : null,
    h('button.toast-x', { onclick: () => dismiss(), 'aria-label': 'Dismiss' }, icon('close')));
  layers.toasts.append(el);
  requestAnimationFrame(() => el.classList.add('in'));
  let t = timeout ? setTimeout(dismiss, timeout) : 0;
  el.addEventListener('mouseenter', () => clearTimeout(t));
  el.addEventListener('mouseleave', () => { if (timeout) t = setTimeout(dismiss, 2000); });
  function dismiss() {
    el.classList.remove('in');
    setTimeout(() => el.remove(), 300);
  }
  return dismiss;
}
