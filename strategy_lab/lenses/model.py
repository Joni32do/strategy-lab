"""The model lens: how can this game be described?

Before any algorithm can find a strategy, someone has to decide what a
*state* is. This lens lays the choices side by side: each game lists two
or three candidate state spaces (``Game.models``), flagged Markov or not,
next to what the engine itself uses right now (the observation of the
player to move) and how the game is built (its class lineage).

Result schema::

    {
      "models":      [{"id", "name", "markov", "state", "actions", "reward",
                       "size", "transition", "note"}],
      "lineage":     ["Game", "MNKGame", "TicTacToe"],
      "family":      {"id", "name", "blurb", "base"},
      "facts":       [[label, value]],     # players, chance, information, ...
      "observation": "<what the player to move sees, as text>",
      "legal":       <number of legal actions now>,
      "classes":     <number of symmetry classes among them>
    }
"""

from __future__ import annotations

from strategy_lab.lenses.base import Lens


class ModelLens(Lens):
    id = "model"
    title = "Model"
    icon = "map"
    blurb = "Which state description makes this game a Markov decision process?"
    concepts = ("mdp", "markov-property", "symmetry")
    order = 60

    def applies(self, game) -> bool:
        return True

    def run(self, session, options):
        g = session.game
        s = session.state
        p = session.to_move()
        legal = g.legal_actions(s) if p >= 0 else []
        try:
            classes = len(g.action_classes(s, legal)) if legal else 0
        except Exception:  # noqa: BLE001 - symmetry is optional
            classes = len(legal)
        viewer = p if p >= 0 else 0
        try:
            obs = g.observation(s, viewer)
        except Exception:  # noqa: BLE001
            obs = ""
        if len(obs) > 600:
            obs = obs[:600] + " ..."
        facts = [
            ["Players", str(g.num_players)],
            ["Chance", "dice, cards or slips" if g.stochastic else "none: fully determined"],
            ["Information", "perfect: everyone sees everything" if g.perfect_information
             else "imperfect: something is hidden"],
            ["Moves", "simultaneous" if g.simultaneous else "one player at a time"],
            ["Steps so far", str(len(session.steps))],
        ]
        return {
            "models": [m.to_json() for m in g.models],
            "lineage": g.lineage(),
            "family": g.family(),
            "facts": facts,
            "observation": obs,
            "legal": len(legal),
            "classes": classes,
        }
