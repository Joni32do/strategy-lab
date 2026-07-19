# Doppelkopf for OpenSpiel

Doppelkopf (the German four-player trick-taking classic) implemented as
an OpenSpiel Python game, with a web UI, a terminal client, and a
trainable "master bot" (perfect-information Monte Carlo search plus a
self-play-trained policy network) that also powers an in-game advice
panel.

## The game in one minute

- 48 cards: a doubled 24-card deck (9, 10, J, Q, K, A in all four suits;
  every card exists twice). Total card points: 240.
- The two players dealt a queen of clubs form the hidden **Re** team;
  the other two are **Kontra**. Teams reveal themselves through play.
- Trumps (strongest first): 10♥ (the "Dulle"), Q♣ Q♠ Q♥ Q♦,
  J♣ J♠ J♥ J♦, A♦ 10♦ K♦ 9♦. All other cards are plain suits ranked
  A > 10 > K > 9. You must follow the led class (trump or plain suit).
- Card points: A=11, 10=10, K=4, Q=3, J=2, 9=0. Re wins with 121+.
- Extra game points: no 90/60/30, schwarz, "against the queens", plus
  special points for catching a fox (A♦), a 40+ point trick
  ("Doppelkopf") and winning the last trick with a J♣ ("Karlchen").
- A player dealt both club queens plays a **silent wedding**: alone as
  Re against three, for triple the score.

Two special rules are toggleable (game parameters `second_dulle` and
`karlchen`, both on by default; see `scoring.Rules`): the later of the
two Dullen beats the earlier one, and winning the last trick with a J-C
scores a Karlchen. Between any other two identical cards the
first-played one still wins.

Simplifications vs. tournament rules: no reservations/solos and no
Re/Kontra announcements.

## Play in the browser

From the `strategy-lab` repository root (its venv has `pyspiel` -- via
the `open-spiel` wheel -- plus `numpy` and `flask` installed):

```
.venv/bin/python -m doppelkopf.web        # http://127.0.0.1:8360
```

You sit south against three bots (rule-based "heuristic" or the
search-based "master"). The **Bot advice** panel shows, on every one of
your turns, how the strongest available bot ranks your legal cards --
expected game points per card, best pick highlighted in your hand.
Query parameters give a quick start: `/?seed=42&opponents=master`.

## Play in the terminal

```
.venv/bin/python -m doppelkopf.cli            # you vs three bots
.venv/bin/python -m doppelkopf.cli --auto     # watch four bots
.venv/bin/python -m doppelkopf.cli --seed 42 --fast
```

## Train the master bot

The bot stack has three layers:

1. `bots.py` -- a rule-based heuristic bot (fast baseline).
2. `search.py` -- PIMC search: sample hidden-hand "worlds" consistent
   with everything the player has seen (`worlds.py`), roll each legal
   card out to the end of the game many times, pick the card with the
   best average return.
3. `policy.py` + `train.py` -- a numpy policy network trained by
   **expert iteration**: the search plays self-play deals, the net
   learns to imitate the search's choices, and once the net beats the
   heuristic baseline head-on it takes over the search's rollouts,
   making the expert itself stronger.

```
.venv/bin/python -m doppelkopf.train                  # default run
.venv/bin/python -m doppelkopf.train --resume         # keep going
.venv/bin/python -m doppelkopf.train --help           # all knobs
```

Training writes `checkpoints/master.npz` (+ `master.json` recording
whether net or heuristic rollouts search stronger); `search.py` and the
web UI pick the best configuration up automatically. Benchmarks on this
machine: PIMC search beats a table of heuristic bots by roughly +0.9
game points per deal (32 worlds).

## Use it as an OpenSpiel game

```python
import pyspiel
import doppelkopf.game  # registers the game

game = pyspiel.load_game("python_doppelkopf")
state = game.new_initial_state()
```

Actions are the 24 card types (`suit * 6 + rank`); the deal is 48
explicit-stochastic chance moves. The game is zero-sum with terminal
rewards; observation strings/tensors and (perfect-recall) information
state strings are provided.

## Files

- `cards.py` -- deck, trump order, trick logic.
- `scoring.py` -- end-of-game scoring, engine-independent.
- `game.py` -- the OpenSpiel game (`python_doppelkopf`).
- `bots.py` -- rule-based bot.
- `worlds.py` -- fast simulator + consistent hidden-hand sampling.
- `policy.py` -- features + numpy MLP policy network.
- `search.py` -- PIMC advisor / MasterBot.
- `train.py` -- expert-iteration training loop.
- `web.py` + `static/` -- the web UI (Flask).
- `cli.py` -- the terminal client.
- Tests: `doppelkopf_test.py` (game rules, scoring, OpenSpiel API),
  `bots_test.py` (heuristic bot), `ai_test.py` (worlds, policy net,
  search, training), `web_test.py` (web API).

Run the tests from the `strategy-lab` repository root:

```
for t in doppelkopf_test bots_test ai_test web_test; do
  .venv/bin/python -m doppelkopf.$t
done
```

## Roadmap

### Bugs
* When a card is played, the other cards are redrawn
* UI (e.g. remaining cards oriented in player direction instead of center)
* ominous names West, North, East -> Werner, Norbert, Esther
* Bot advice takes some space of the UI, as well as Bots at top

### Features
* Instead of hints while playing, game review after the game
