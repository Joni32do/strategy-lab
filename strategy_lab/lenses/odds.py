"""The odds lens: probability, surprise, and what each move is worth.

Three questions, answered for any game with dice or cards that are not
hidden from anyone:

1. **What just happened, and how likely was it?** The last chance event:
   its probability, its surprise ``-log2 p`` and the entropy of the whole
   distribution (the average surprise), with the full distribution if small.
2. **How lucky has this game been?** The total surprise of all chance
   events so far, compared with the expected total (the sum of entropies).
3. **What is each move worth?** Monte Carlo: play every legal move, then
   finish the game many times with a rollout policy, and count wins. The
   win rate per move is shown on the board.

Result schema::

    {
      "last":   null | {"text", "prob", "surprise", "entropy", "outcomes",
                        "distribution": null | [{"a", "p", "label", "hit"}]},
      "luck":   {"events", "surprise", "expected"},          # bits
      "moves":  null | [{"a", "label", "wins", "draws", "n", "rate", "mean",
                         "stderr"}],                          # best first
      "now":    null | {"rate", "n"},                         # win chance now
      "policy": "<rollout policy name>",
      "overlay": {"actions": {...}}                           # see lenses.base
    }
"""

from __future__ import annotations

import math
import time

from strategy_lab.core.game import CHANCE, Game
from strategy_lab.core.match import play_out
from strategy_lab.core.policy import RandomPolicy
from strategy_lab.lenses.base import Lens, overlay


class OddsLens(Lens):
    id = "odds"
    title = "Odds"
    icon = "percent"
    blurb = "How likely was that roll, and which move wins most often?"
    concepts = ("probability", "expected-value", "entropy", "law-of-large-numbers")
    order = 10
    options = (
        {"name": "rollouts", "label": "Games per move", "type": "int", "default": 80,
         "min": 10, "max": 2000, "step": 10},
        {"name": "policy", "label": "Rollout players", "type": "choice", "default": "random",
         "choices": ["random", "best bot"]},
    )

    #: Wall-clock budget for the Monte Carlo part.
    budget_s = 1.2

    def applies(self, game: Game) -> bool:
        return game.stochastic and game.perfect_information

    def run(self, session, options):
        g = session.game
        out: dict = {"last": None, "moves": None, "now": None}

        # 1 + 2: chance events in the log
        surprise = expected = 0.0
        events = 0
        last = None
        for st in session.steps:
            if st.player == CHANCE and st.chance:
                events += 1
                if st.chance.get("surprise") is not None:
                    surprise += st.chance["surprise"]
                expected += st.chance.get("entropy") or 0.0
                last = st
        if last is not None:
            dist = last.chance.get("distribution")
            if dist:
                dist = [{**d, "hit": d["a"] == last.action} for d in dist]
            out["last"] = {"text": last.text, "prob": last.chance["prob"],
                           "surprise": last.chance.get("surprise"),
                           "entropy": last.chance.get("entropy"),
                           "outcomes": last.chance.get("outcomes"), "distribution": dist}
        out["luck"] = {"events": events, "surprise": round(surprise, 3),
                       "expected": round(expected, 3)}

        # 3: Monte Carlo move values for the player to move
        p = session.to_move()
        per_move = self.option(options, "rollouts")
        policy_name = self.option(options, "policy")
        policies = [self._policy(g, policy_name) for _ in range(g.num_players)]
        out["policy"] = "random players" if policy_name == "random" else "the strongest bot"
        if p >= 0 and not session.terminal:
            legal = g.legal_actions(session.state)
            rows = []
            deadline = time.monotonic() + self.budget_s
            n_each = max(1, per_move)
            for a in legal:
                child = g.apply_action(session.state, a)
                wins = draws = n = 0
                total = 0.0
                for i in range(n_each):
                    if time.monotonic() > deadline and n >= 5:
                        break
                    rets, _, _ = play_out(g, policies, f"odds:{session.seed}:{a}:{i}",
                                          state=g.copy_state(child))
                    outcome = g.outcome(rets, p)
                    wins += outcome == "win"
                    draws += outcome == "draw"
                    total += rets[p]
                    n += 1
                rate = (wins + 0.5 * draws) / n if n else 0.0
                mean = total / n if n else 0.0
                rows.append({"a": a, "label": g.action_label(session.state, a), "wins": wins,
                             "draws": draws, "n": n, "rate": round(rate, 4),
                             "mean": round(mean, 4),
                             "stderr": round(math.sqrt(rate * (1 - rate) / n), 4) if n else None})
            rows.sort(key=lambda r: -r["rate"])
            out["moves"] = rows
            out["overlay"] = overlay({r["a"]: r["rate"] * 100 for r in rows}, fmt="{:.0f}%")
            if rows:
                n_all = sum(r["n"] for r in rows)
                out["now"] = {"rate": rows[0]["rate"], "n": n_all}
        else:
            out["overlay"] = {"actions": {}}
        return out

    @staticmethod
    def _policy(g: Game, name: str):
        if name == "random" or not g.bots:
            return RandomPolicy()
        best = max(g.bots, key=lambda b: b.stars)
        return g.make_policy(best.id)
