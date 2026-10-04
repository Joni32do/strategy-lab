# Scenes

A game never draws. {meth}`~strategy_lab.core.game.Game.scene` returns a
list of *parts*; each part names the frontend view that renders it. Build
them with the helpers in {mod}`strategy_lab.core.scene`:

```python
from strategy_lab.core import scene

def scene(self, s, viewer):
    board = scene.grid(3, 3, [scene.cell(action=i) for i in range(9)])
    return scene.scene([board], status="Your move")
```

| Helper | View | For |
| --- | --- | --- |
| `grid(rows, cols, cells)` | `GridView` | boards, grid worlds, chess, Snakes & Ladders |
| `track(spaces, tokens)` | `TrackView` | Monopoly ring, Life road |
| `dice(dice)` | `DiceView` | dice with pips, colored, clickable |
| `heaps(heaps)` | `HeapsView` | Nim |
| `matrix(...)` | `MatrixView` | payoff tables |
| `arms(arms)` | `ArmsView` | bandits |
| `sheet(...)` | `SheetView` | Qwixx score sheets |
| `table(...)` | `CardsView` | card tables |
| `bars`, `kv`, `buttons`, `text` | panels | scores, finances, choices, fallback |
| `custom(view, **data)` | `views/custom/<view>.js` | anything else |

## Interaction and lens badges

Any element with an `action` is clickable and plays that action. Lenses
return overlays keyed by action (`{"actions": {"4": {"text": "Win", "tone":
"best"}}}`), and every view puts the badge on the element that plays it.
Legal actions that appear nowhere on the board are listed under the board.

## A custom view

```javascript
// web/js/views/custom/hex.js  -- loaded the first time a "hex" part appears
import { View } from '../view.js';
import { registerView } from '../registry.js';

export class HexView extends View {
  static type = 'hex';
  render(part) { /* build DOM in this.el, use this.actionable(el, a) */ }
}
registerView(HexView);
```
