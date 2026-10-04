/* Which View class draws which scene part.
 *
 * Lookup order for part.view:
 *   1. the active skin's override (skins/*.js: `views: {grid: SketchGridView}`)
 *   2. a game-specific view in views/custom/<type>.js (loaded on first use;
 *      the module calls registerView)
 *   3. the stock views below
 *   4. the base View (prints the JSON: handy while you build a new part) */

import { View } from './view.js';
import { GridView } from './grid.js';
import { TrackView } from './track.js';
import { DiceView } from './dice.js';
import { HeapsView } from './heaps.js';
import { MatrixView } from './matrix.js';
import { ArmsView } from './arms.js';
import { SheetView } from './sheet.js';
import { CardsView } from './cards.js';
import { BarsView, ButtonsView, KvView, TextView } from './panels.js';

const STOCK = {};
for (const cls of [GridView, TrackView, DiceView, HeapsView, MatrixView, ArmsView, SheetView,
  CardsView, BarsView, KvView, ButtonsView, TextView]) {
  STOCK[cls.type] = cls;
}

const CUSTOM = {};
const tried = new Set();

/** Register a game-specific view class (its static `type` is the part name). */
export function registerView(cls) { CUSTOM[cls.type] = cls; }

/** Load views/custom/<type>.js for unknown part types (once). */
export async function ensureViews(types) {
  const missing = [...new Set(types)].filter((t) => !STOCK[t] && !CUSTOM[t] && !tried.has(t));
  await Promise.all(missing.map(async (t) => {
    tried.add(t);
    if (!/^[a-z][a-z0-9-]*$/.test(t)) return;
    try { await import(`./custom/${t}.js`); } catch (e) { console.warn(`no view for "${t}"`, e); }
  }));
}

export function viewClass(type, skin) {
  return skin?.views?.[type] || CUSTOM[type] || STOCK[type] || View;
}
