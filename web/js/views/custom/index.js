/* Game-specific views live here, one file per part type: views/custom/<type>.js.
 * The registry imports the file the first time a scene contains that part
 * type, so there is nothing to register by hand. Template:
 *
 *   import { View } from '../view.js';
 *   import { registerView } from '../registry.js';
 *
 *   export class HexView extends View {
 *     static type = 'hex';
 *     render(part) { ... build DOM in this.el, use this.actionable(el, a) ... }
 *   }
 *   registerView(HexView);
 *
 * The Python side emits it with scene.custom("hex", ...). */
