"""The cards lens: write your strategy as a stack of rule cards.

A rule card is one readable idea ("Block the win", "Hold at 20"). A stack
of cards, read top to bottom, is a complete policy (see
:class:`~strategy_lab.core.policy.RulePolicy`). This lens shows, for the
current position, what your stack would do and which card decides. The
"simulate 100 games" button lives at ``POST /api/simulate``.

Options: ``stack`` (list of card ids, top first).

Result schema::

    {
      "cards":   [{"id", "name", "desc", "kind", "icon"}],   # the palette
      "bots":    [{"id", "name", "stars", "cards"}],        # stacks to study
      "trace":   null | {"action", "label", "card", "reason",
                         "vetoed": [{"card", "actions": [labels]}],
                         "steps": [{"card", "kind", "result"}]},
      "overlay": {"actions": {...}}   # the stack's choice is marked "best"
    }
"""

from __future__ import annotations

import random

from strategy_lab.core.policy import RulePolicy
from strategy_lab.lenses.base import Lens


class CardsLens(Lens):
    id = "cards"
    title = "Cards"
    icon = "cards"
    blurb = "Write your strategy as rule cards and test it on 100 games."
    concepts = ("policy", "rule-cards", "simulation", "law-of-large-numbers")
    order = 5

    def applies(self, game) -> bool:
        return bool(game.cards()) and game.num_players >= 2

    def run(self, session, options):
        g = session.game
        stack_ids = [c for c in (options.get("stack") or []) if c in {x.id for x in g.cards()}]
        out = {
            "cards": [c.to_json() for c in g.cards()],
            "bots": [{"id": b.id, "name": b.name, "stars": b.stars, "cards": list(b.cards)}
                     for b in g.bots if not b.policy],
            "trace": None,
            "overlay": {"actions": {}},
        }
        p = session.to_move()
        if p < 0 or session.terminal or not stack_ids:
            return out
        s = session.state
        policy = RulePolicy([g.card(c) for c in stack_ids])
        decision = policy.decide(g, s, p, random.Random(20260710))
        steps = self._steps(g, s, p, stack_ids)
        a = decision["action"]
        out["trace"] = {
            "action": a if decision["reason"] != "random" else None,
            "label": g.action_label(s, a) if decision["reason"] != "random" else "",
            "card": decision["card"],
            "reason": decision["reason"],
            "vetoed": [{"card": cid, "actions": [g.action_label(s, x) for x in acts]}
                       for cid, acts in decision["vetoed"]],
            "steps": steps,
        }
        if decision["reason"] != "random":
            out["overlay"] = {"actions": {str(a): {"text": "stack", "tone": "best"}}}
        return out

    @staticmethod
    def _steps(g, s, p, stack_ids):
        """What every card in the stack says on its own (for the stack view)."""
        rows = []
        legal = g.legal_actions(s)
        rng = random.Random(20260710)
        for cid in stack_ids:
            card = g.card(cid)
            if card.kind == "avoid":
                vetoed = [g.action_label(s, a) for a in legal if card.fn(g, s, a, p)]
                rows.append({"card": cid, "kind": "avoid",
                             "result": ("vetoes " + ", ".join(vetoed)) if vetoed else "no veto"})
            else:
                a = card.fn(g, s, legal, p, rng)
                rows.append({"card": cid, "kind": "pick",
                             "result": g.action_label(s, a) if a is not None else "no opinion"})
        return rows
