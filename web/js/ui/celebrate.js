/* Celebrations: toasts for unlocks, stars and concept cards, a chapter
 * opening card, and a little confetti. Listens to store 'achieved'. */

import { api } from '../api.js';
import { h } from '../dom.js';
import { icon } from '../icons.js';
import { store } from '../store.js';
import { go } from '../router.js';
import { md } from '../text.js';
import { modal, closeModal, toast } from './shell.js';
import { openCheatsheet } from './cheatsheet.js';

const details = {};

async function challengeTitle(gameId, cid) {
  try {
    details[gameId] ||= await api.game(gameId);
    return details[gameId].challenges.find((c) => c.id === cid)?.title || cid;
  } catch {
    return cid;
  }
}

export function initCelebrate() {
  store.on('achieved', async (a) => {
    for (const [g, ids] of Object.entries(a.stars || {})) {
      for (const cid of ids) {
        toast(h('span', h('strong', 'Star earned: '), await challengeTitle(g, cid)), { icon: 'star', tone: 'star' });
      }
    }
    for (const cid of a.concepts || []) {
      const c = (await store.loadConcepts(true)).concepts.find((x) => x.id === cid);
      toast(h('span', h('strong', 'New concept card: '), c?.title || cid), {
        icon: 'cheatsheet', tone: 'good', timeout: 6000,
        actions: [{ label: 'Open', onclick: () => openCheatsheet(cid) }],
      });
    }
    for (const g of a.games || []) {
      const meta = store.gameMeta(g);
      toast(h('span', h('strong', 'Unlocked: '), meta?.name || g), {
        icon: 'unlock', tone: 'good', timeout: 7000,
        actions: [{ label: 'Play', onclick: () => go(`/game/${g}`) }],
      });
    }
    if (a.chapters?.length) chapterCard(a.chapters[0]);
    if (Object.keys(a.stars || {}).length) confetti(40);
  });
}

function chapterCard(id) {
  const ch = store.chapter(id);
  if (!ch) return;
  confetti(90);
  const first = ch.families.flatMap((f) => f.games).sort((a, b) => a.order - b.order)[0];
  modal(h('div.chapter-card', { style: { '--cc': `var(--c-${ch.color})` } },
    h('div.chapter-badge.big', icon(ch.icon)),
    h('div.upper.muted', 'New chapter'),
    h('h2', ch.title), h('p.chapter-q', ch.question), md(ch.intro),
    h('div.row.end',
      h('button.btn', { onclick: () => closeModal() }, 'Later'),
      first ? h('button.btn.primary', { onclick: () => { closeModal(); go(`/game/${first.id}`); } }, icon('play'), `Play ${first.name}`) : null)));
}

/* A short burst of confetti. Respects the animation setting. */
export function confetti(count = 70) {
  if (store.setting('motion') === false || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const canvas = h('canvas.confetti');
  document.body.append(canvas);
  const ctx = canvas.getContext('2d');
  const W = (canvas.width = innerWidth);
  const H = (canvas.height = innerHeight);
  const styles = getComputedStyle(document.documentElement);
  const colors = ['--p0', '--p1', '--p2', '--p3', '--p4', '--c-amber'].map((v) => styles.getPropertyValue(v).trim() || '#fff');
  const parts = Array.from({ length: count }, () => ({
    x: W / 2 + (Math.random() - 0.5) * W * 0.3, y: H * 0.35,
    vx: (Math.random() - 0.5) * 14, vy: -Math.random() * 13 - 4,
    r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
    w: 6 + Math.random() * 6, h: 4 + Math.random() * 4,
    c: colors[Math.floor(Math.random() * colors.length)],
  }));
  const t0 = performance.now();
  function frame(t) {
    const dt = Math.min(2, (t - (frame.last || t)) / 16.7);
    frame.last = t;
    ctx.clearRect(0, 0, W, H);
    for (const p of parts) {
      p.vy += 0.35 * dt;
      p.vx *= 0.99;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.r += p.vr * dt;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.r);
      ctx.fillStyle = p.c;
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx.restore();
    }
    if (t - t0 < 2200) requestAnimationFrame(frame);
    else canvas.remove();
  }
  requestAnimationFrame(frame);
}
