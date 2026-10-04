"""Core of the lab: the game base class, policies, sessions, search, matches.

The names most game files need are re-exported here::

    from strategy_lab.core import Game, Bot, Rulebook, pick, avoid, scene
"""

from strategy_lab.core import scene
from strategy_lab.core.game import (
    CHANCE, TERMINAL, Action, Bot, Card, Challenge, Game, Model, Param, Rulebook,
    RANDOM_BOT, avoid, pick,
)
from strategy_lab.core.policy import (
    FunctionPolicy, MixedPolicy, Policy, RandomPolicy, RulePolicy,
)
from strategy_lab.core.search import SearchPolicy, Solver, TooBig, alphabeta
from strategy_lab.core.session import ReplayError, Seat, Session

__all__ = [
    "CHANCE", "TERMINAL", "Action", "Bot", "Card", "Challenge", "Game", "Model",
    "Param", "Rulebook", "RANDOM_BOT", "avoid", "pick", "scene",
    "Policy", "RandomPolicy", "RulePolicy", "MixedPolicy", "FunctionPolicy",
    "SearchPolicy", "Solver", "TooBig", "alphabeta",
    "Seat", "Session", "ReplayError",
]
