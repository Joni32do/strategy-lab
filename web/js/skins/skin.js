/* Skin: a different way to display the same games.
 *
 * A skin is two things:
 *   - CSS tokens under [data-skin="<id>"] in css/skins.css (colors, fonts),
 *   - optional View subclasses in `views` that redraw parts their own way.
 *
 * The game logic never knows which skin is active. */

export class Skin {
  static id = 'base';
  static label = 'Base';
  static blurb = '';

  constructor() {
    /** type -> View subclass, e.g. {grid: SketchGridView} */
    this.views = {};
  }

  apply() {
    document.documentElement.dataset.skin = this.constructor.id;
  }

  get id() { return this.constructor.id; }
}
