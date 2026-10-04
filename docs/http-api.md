# HTTP API

The full list with descriptions is in {mod}`strategy_lab.web.app`. The
central call is `POST /api/play`:

```json
{
  "game": "tictactoe",
  "params": {},
  "seed": 1234,
  "seats": [{"kind": "human"}, {"kind": "bot", "bot": "minnie"}],
  "log": [{"p": 0, "a": 4}, {"p": 1, "a": 0}],
  "action": 8,
  "mode": "play",
  "sid": "browser-session-id",
  "since": 0
}
```

- `mode`: `play` (advance until a human must act), `step` (one bot or
  chance move), anything else (no automatic moves).
- `undo: true` rewinds to before the last human action.
- The response carries `log`, `steps` (captions, chance probabilities),
  `scene`, `status`, `legal`, `humanTurn`, `terminal`, `returns`,
  `outcome`, `replayError` and, when a game ends, `achieved`
  (new games, chapters, stars and concept cards).

`POST /api/lens/<id>` takes the same session fields plus `options`.
`POST /api/simulate` takes `game`, `params`, `stack`, `bot`, `n`, `seed`.
