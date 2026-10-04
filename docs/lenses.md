# Lenses

A lens is an analysis panel next to the board. Each lens decides which
games it applies to and turns the current session into JSON; a matching
JavaScript view draws it and may put badges on the board.

| Lens | Applies to | Shows |
| --- | --- | --- |
| **Cards** | games with rule cards | your card stack, which card decides now, simulation vs a bot |
| **Odds** | games with visible chance | last roll probability, surprise and entropy, Monte Carlo win rate per move |
| **Game tree** | 2-player, perfect information, no chance | exact minimax values, symmetry classes, principal variation |
| **Nash** | simultaneous matrix games | equilibria, best responses, your entropy, regret matching |
| **Learn** | single-player MDPs | value iteration / Q-learning / bandit algorithms, learning curves |
| **Model** | every game | candidate state spaces (Markov or not), class lineage |
| **Trading** | Catan | position strength and the trade coefficient |

## Writing a lens

```python
from strategy_lab.lenses.base import Lens, overlay

class ParityLens(Lens):
    id = "parity"
    title = "Parity"
    icon = "sigma"
    blurb = "Is the counter even?"

    def applies(self, game):
        return game.id == "race_to_50"

    def run(self, session, options):
        values = {a: float((session.state.total + a) % 2 == 0)
                  for a in session.game.legal_actions(session.state)}
        return {"even": session.state.total % 2 == 0, "overlay": overlay(values)}
```

Put it in `strategy_lab/lenses/parity.py`; it is discovered automatically.
Without a `web/js/lenses/parity.js`, the panel shows the raw JSON, which is
enough while you build it. A view is a class:

```javascript
import { h } from '../dom.js';
import { LensView } from './lens.js';

export default class ParityLens extends LensView {
  render(r) { this.body.append(h('p', r.even ? 'even' : 'odd')); }
}
```
