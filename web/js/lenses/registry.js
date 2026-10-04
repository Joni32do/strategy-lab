/* Lens views by id: lenses/<id>.js is imported on first use and must
 * `export default` a LensView subclass. Missing files fall back to the
 * base LensView (raw JSON). */

import { LensView } from './lens.js';

const cache = {};

export async function lensClass(id) {
  if (cache[id]) return cache[id];
  let cls = LensView;
  if (/^[a-z][a-z0-9-]*$/.test(id)) {
    try {
      const mod = await import(`./${id}.js`);
      cls = mod.default || LensView;
    } catch (e) {
      console.warn(`no view for lens "${id}"`, e);
    }
  }
  cache[id] = cls;
  return cls;
}
