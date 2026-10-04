/* App-wide state: profile, progress, catalog, concepts. One instance.
 *
 * Events (store.on(name, fn)):
 *   'profile'   profile or progress changed
 *   'catalog'   catalog reloaded
 *   'achieved'  something new was unlocked/earned: {games, chapters, stars, concepts}
 *   'reloaded'  the dev server restarted (Python changed)
 */

import { api } from './api.js';

class Store {
  constructor() {
    this.profile = null;
    this.progress = null;
    this.stats = null;
    this.catalog = null;
    this.concepts = null;
    this.dev = false;
    this._handlers = {};
  }

  on(name, fn) {
    (this._handlers[name] ||= new Set()).add(fn);
    return () => this._handlers[name].delete(fn);
  }

  emit(name, detail) {
    for (const fn of this._handlers[name] || []) {
      try { fn(detail); } catch (e) { console.error(e); }
    }
  }

  async load() {
    const [prof, cat] = await Promise.all([api.profile(), api.catalog()]);
    this._setProfile(prof);
    this.catalog = cat;
    return this;
  }

  _setProfile(d) {
    this.profile = d.profile;
    this.progress = d.progress || this.progress;
    if (d.stats) this.stats = d.stats;
    document.documentElement.dataset.motion = this.profile.settings.motion === false ? 'off' : 'on';
  }

  async refresh() {
    const [prof, cat] = await Promise.all([api.profile(), api.catalog()]);
    this._setProfile(prof);
    this.catalog = cat;
    this.emit('profile', this.profile);
    this.emit('catalog', this.catalog);
  }

  async loadConcepts(force = false) {
    if (!this.concepts || force) this.concepts = await api.concepts();
    return this.concepts;
  }

  setting(key) { return this.profile?.settings?.[key]; }

  async patch(patch) {
    const d = await api.patchProfile(patch);
    this._setProfile(d);
    this.emit('profile', this.profile);
    if (patch.settings && 'unlockAll' in patch.settings) await this.refresh();
    return this.profile;
  }

  tutorialDone(step) { return (this.profile?.tutorial?.done || []).includes(step); }

  async markTutorial(step) {
    if (this.tutorialDone(step)) return;
    const done = [...(this.profile.tutorial.done || []), step];
    await this.patch({ tutorial: { done } });
  }

  /* A server response carried `achieved`: refresh and celebrate. */
  async achieved(a) {
    if (!a) return;
    const any = a.games?.length || a.chapters?.length || a.concepts?.length
      || Object.keys(a.stars || {}).length;
    await this.refresh();
    if (a.concepts?.length) this.concepts = null;
    if (any) this.emit('achieved', a);
  }

  /* Lookup helpers over the catalog. */
  gameMeta(id) {
    for (const ch of this.catalog?.chapters || []) {
      for (const fam of ch.families) {
        const g = fam.games.find((x) => x.id === id);
        if (g) return { ...g, chapterTitle: ch.title, chapterColor: ch.color, familyName: fam.name };
      }
    }
    return null;
  }

  chapter(id) { return (this.catalog?.chapters || []).find((c) => c.id === id); }

  /* Games in unlock-path order (for "next game" suggestions). */
  pathOrder() {
    const out = [];
    for (const ch of this.catalog?.chapters || []) {
      if (ch.id === 'workbench') continue;
      const games = ch.families.flatMap((f) => f.games).sort((a, b) => a.order - b.order);
      out.push(...games);
    }
    return out;
  }

  nextGame() {
    return this.pathOrder().find((g) => g.unlocked && !g.finished) || null;
  }
}

export const store = new Store();
