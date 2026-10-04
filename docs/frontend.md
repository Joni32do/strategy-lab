# Frontend

Plain ES modules, no build step, served by Flask from `web/`.

| Module | Role |
| --- | --- |
| `js/main.js` | boot, routes, dev live reload |
| `js/store.js` | profile, progress, catalog, events (`achieved`, `reloaded`) |
| `js/ui/gallery.js` | chapter map: chapters, families (base classes), game tiles |
| `js/ui/game-page.js` | play, watch, undo, replay, lens dock |
| `js/ui/tutorial.js` | intro slides and coach marks |
| `js/ui/cheatsheet.js` | concept cards drawer (KaTeX formulas) |
| `js/ui/history-page.js` | profile, records, replays |
| `js/views/*.js` | one `View` subclass per scene part |
| `js/lenses/*.js` | one `LensView` subclass per lens id |
| `js/skins/*.js` | `Skin` subclasses with view overrides |

## Skins

A skin is CSS tokens in `css/skins.css` under `[data-skin="<id>"]` plus an
optional map of View overrides:

```javascript
export class PaperSkin extends Skin {
  static id = 'paper';
  static label = 'Paper';
  constructor() { super(); this.views = { grid: SketchGridView, dice: PaperDiceView }; }
}
```

Three skins ship: **Lab** (default, dark), **Paper** (notebook, hand-drawn
boards) and **Minimal** (monochrome, boards as characters).

## Icons and fonts

Icons are referenced by name (`icon = "dice"`) and stored in
`web/assets/icons.json`, built from Lucide by `scripts/build_icons.py`.
Fonts (Bricolage Grotesque, Inter, JetBrains Mono, Caveat) and KaTeX are
vendored in `web/vendor/` with their licenses, so the app works offline.
