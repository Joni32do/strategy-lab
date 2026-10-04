# Adding a game

## 1. Scaffold

```bash
uv run python -m strategy_lab new race_to_50 --name "Race to 50"
uv run python -m strategy_lab serve --dev
```

The new file `strategy_lab/games/race_to_50.py` is a complete, playable
draft. Open the Workbench chapter in the gallery and play it.

## 2. Iterate while playing

Keep the game open in the browser and edit the Python file. On save, the
dev server restarts and the page replays your current game under the new
rules. If a logged move became illegal, a notice says where the replay
stopped and the game continues from there. A syntax error does not crash
the server; the Workbench shows the traceback instead.

## 3. The contract

Implement these methods (see {class}`~strategy_lab.core.game.Game`):

| Method | Returns |
| --- | --- |
| `initial_state()` | the start state (no randomness) |
| `current_player(s)` | seat index, or `CHANCE` |
| `legal_actions(s)` | list of `int` or `str` |
| `move(s, a)` | nothing: change `s` in place |
| `chance_outcomes(s)` | `[(outcome, probability), ...]` at chance nodes |
| `is_terminal(s)` | bool |
| `winner(s)` or `returns(s)` | winning seat, or one float per seat |
| `scene(s, viewer)` | the view model (see [Scenes](scenes.md)) |

Rules of thumb:

- **All randomness is a chance node.** Roll dice by returning `CHANCE` from
  `current_player` and listing outcomes. Never call `random` inside rules.
  For a full shuffle, sample a seed as the outcome (override
  `sample_chance`) and shuffle with `random.Random(seed)`.
- **Actions are `int` or `str`.** They travel through JSON.
- **Hidden information:** hide it in `scene(s, viewer)`, return only what a
  player knows in `observation(s, player)`, and mark private log steps with
  `privacy(s, a, player)`.

## 4. Inherit when you can

Before writing rules from scratch, look in `strategy_lab/families/`. A
Gomoku variant is four lines:

```python
from strategy_lab.families.board import MNKGame

class Gomoku(MNKGame):
    id = "gomoku"
    name = "Gomoku"
    tagline = "Five in a row on a big board."
    rows, cols, k = 15, 15, 5
```

It inherits the rules, the symmetry group, the heuristic, the scene and
the rule cards.

## 5. Strategy: cards and bots

```python
from strategy_lab.core import Bot, pick, avoid

@pick("greedy", "Take the most", "Always take the biggest step.", "bolt")
def card_greedy(self, s, candidates, player, rng):
    return max(candidates)

bots = (Bot("greedy-gus", "Greedy Gus", "Always the biggest step.", 2, cards=("greedy",)),)
```

A bot plays a stack of cards, or a custom policy (`Bot(..., policy="method_name")`
where the method returns a {class}`~strategy_lab.core.policy.Policy`).

## 6. Teach something

Set `chapter`, `order`, `concepts` (ids from `strategy_lab/learn/concepts.py`),
`challenges` (they earn stars), `models` (ways to describe the game as an
MDP) and a `rulebook`. Remove `draft = True` to put the game on the path.

## 7. Check

```bash
uv run python -m strategy_lab check race_to_50
```

The conformance suite plays your game randomly, with every bot and every
card, replays its logs and serializes every scene.
