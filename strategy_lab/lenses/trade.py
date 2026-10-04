"""The trading lens: when is helping a rival worth it? (Catan only.)

Three things the policy of :class:`~strategy_lab.games.catan.policy.StrategicTradingPlayer`
is built from, shown for the current position:

1. **Position strength** of every player in ``[0, 1]``: how close they are to
   winning (victory points, production, room to expand), each term with its
   own weight.
2. **The trade coefficient** ``lambda(opponent strength)``: a logistic curve.
   A deal is judged by ``net = my_gain - lambda * their_gain`` and accepted if
   ``net >= margin + premium_per_vp * (VP the partner is ahead)``. A weak
   partner gets lambda near 0 (pure self-interest), a leader gets a high
   lambda, and a partner within ``veto_vp_margin`` of winning is vetoed.
3. **Recent trade decisions**: the last offers, answers and confirmations of
   the game, re-judged with the knobs of this panel (what the rule *would*
   say), next to what the players actually did.

The lens replays the session once (cheap, no copies) and never changes it.

Result schema::

    {
      "perspective": <seat whose view the markers take>,
      "players": [{"seat", "name", "vp", "publicVp", "strength", "vpTerm",
                   "production", "productionTerm", "buildable", "reachTerm"}],
      "curve":   {"points": [{"s": 0.0, "lambda": 0.01}, ... 41 points],
                  "lamMax", "midpoint", "steepness", "vetoVpMargin", "vpsToWin"},
      "markers": [{"seat", "name", "strength", "lambda", "vetoed"}],  # rivals of the perspective
      "rule":    {"accept": "net >= required", "margin", "premiumPerVp"},
      "current": null | {"responder", "offerer", "give", "get", ...reasoning},
      "decisions": [{"step", "actor", "actorName", "kind": "offer" | "answer" | "deal" | "cancel",
                     "actual": "ACCEPT" | "REJECT" | "OFFER:..." | "CONFIRM:RED" | "CANCEL",
                     "with", "withName", "give": [5], "get": [5],       # cards of WOOD BRICK SHEEP WHEAT ORE
                     "reasoning": null | {"oppStrength", "lambda", "myGain", "theirGain",
                                           "net", "required", "myVp", "oppVp", "vetoed", "ok"},
                     "verdict": "accept" | "decline" | "veto" | "ok" | "cancel"}]   # newest last
    }

``give`` and ``get`` are from the point of view of the *actor* of the step
(what they hand over and what they receive). ``reasoning`` is the rule applied
from the actor's seat to the partner. For an answer the partner is the
offerer, for an offer the most promising rival (acceptable ones first, then highest ``net``).
"""

from __future__ import annotations

from catanatron.models.enums import ActionPrompt
from catanatron.models.player import Color
from catanatron.state_functions import get_actual_victory_points, get_visible_victory_points

from strategy_lab.core.game import Game
from strategy_lab.games.catan.actions import kind
from strategy_lab.games.catan.policy import (
    MetricWeights, TradeParams, evaluate_trade, position_strength, trade_coefficient)
from strategy_lab.lenses.base import Lens

WEIGHT_OPTIONS = (
    ("vp", "VP weight", 0, 1, 0.01),
    ("production", "Production weight", 0, 1, 0.01),
    ("expansion", "Expansion weight", 0, 1, 0.01),
    ("prod_norm", "Production counts as full at (pips)", 4, 24, 1),
    ("expansion_norm", "Expansion counts as full at (nodes)", 2, 16, 1),
    ("block_weight", "Blocking preference (play, not trade)", 0, 3, 0.1),
)
TRADE_OPTIONS = (
    ("lam_max", "Lambda ceiling", 0, 5, 0.1),
    ("lam_steepness", "Lambda steepness", 1, 20, 0.5),
    ("lam_midpoint", "Lambda midpoint (rival strength)", 0, 1, 0.02),
    ("veto_vp_margin", "Veto within this many VP of winning", 0, 4, 1),
    ("margin", "Minimum net value", 0, 2, 0.05),
    ("premium_per_vp", "Premium per VP the partner leads", 0, 2, 0.05),
    ("scarcity_weight", "Scarcity value", 0, 3, 0.1),
    ("need_weight", "Need value", 0, 4, 0.1),
    ("base_value", "Base value of a card", 0, 2, 0.1),
)
TRADE_KINDS = ("OFFER", "ACCEPT", "REJECT", "CONFIRM", "CANCEL")


def _option(name, label, lo, hi, step, default):
    integer = name == "veto_vp_margin"
    return {"name": name, "label": label, "type": "int" if integer else "float",
            "default": default, "min": lo, "max": hi, "step": step}


def _defaults() -> tuple[tuple[dict, ...], dict]:
    w, t = MetricWeights(), TradeParams()
    opts = [_option(n, lb, lo, hi, st, getattr(w, n)) for n, lb, lo, hi, st in WEIGHT_OPTIONS]
    opts += [_option(n, lb, lo, hi, st, getattr(t, n)) for n, lb, lo, hi, st in TRADE_OPTIONS]
    opts.append({"name": "history", "label": "Decisions shown", "type": "int", "default": 8,
                 "min": 1, "max": 30, "step": 1})
    return tuple(opts), {"weights": w, "trade": t}


class TradeLens(Lens):
    id = "trade"
    title = "Trading"
    icon = "handshake"
    blurb = "How strong is each player, and how much do you let a rival gain?"
    concepts = ("multi-agent", "negotiation")
    order = 60
    options, _ = _defaults()

    def applies(self, game: Game) -> bool:
        return game.id == "catan"

    # ------------------------------------------------------------------ run
    def knobs(self, options: dict) -> tuple[MetricWeights, TradeParams]:
        weights = MetricWeights(**{n: float(self.option(options, n)) for n, *_ in WEIGHT_OPTIONS})
        trade = TradeParams(**{n: (int if n == "veto_vp_margin" else float)(self.option(options, n))
                               for n, *_ in TRADE_OPTIONS})
        return weights, trade

    def run(self, session, options: dict) -> dict:
        game = session.game
        weights, tp = self.knobs(options)
        s = session.state
        if s.game is None:
            return {"players": [], "curve": None, "markers": [], "decisions": [], "current": None}
        eng = s.game
        st = eng.state
        names = [game.seat_label(i) for i in range(game.num_players)]
        strengths = {}
        players = []
        for seat, color in enumerate(st.colors):
            strength, d = position_strength(eng, color, weights)
            strengths[seat] = strength
            players.append({
                "seat": seat, "name": names[seat], "vp": get_actual_victory_points(st, color),
                "publicVp": get_visible_victory_points(st, color),
                "strength": round(strength, 3), "vpTerm": round(d["vp_term"], 3),
                "production": round(d["production"], 3),
                "productionTerm": round(d["prod_term"], 3), "buildable": d["buildable"],
                "reachTerm": round(d["exp_term"], 3)})
        mover = st.current_player_index
        perspective = mover if s.pending is None and mover >= 0 else 0
        markers = []
        for seat, color in enumerate(st.colors):
            if seat == perspective:
                continue
            vetoed = get_actual_victory_points(st, color) >= eng.vps_to_win - tp.veto_vp_margin
            markers.append({"seat": seat, "name": names[seat],
                            "strength": round(strengths[seat], 3),
                            "lambda": round(trade_coefficient(strengths[seat], tp), 3),
                            "vetoed": vetoed})
        curve = {"points": [{"s": i / 40, "lambda": round(trade_coefficient(i / 40, tp), 4)}
                            for i in range(41)],
                 "lamMax": tp.lam_max, "midpoint": tp.lam_midpoint, "steepness": tp.lam_steepness,
                 "vetoVpMargin": tp.veto_vp_margin, "vpsToWin": eng.vps_to_win}
        return {
            "perspective": perspective, "players": players, "curve": curve, "markers": markers,
            "rule": {"accept": "net >= required", "margin": tp.margin,
                     "premiumPerVp": tp.premium_per_vp},
            "current": self.current(game, s, weights, tp),
            "decisions": self.decisions(session, weights, tp, int(self.option(options, "history"))),
        }

    # ------------------------------------------------------------ reasoning
    @staticmethod
    def _info(info: dict) -> dict:
        return {"oppStrength": info["opp_strength"], "lambda": info["lambda"],
                "myGain": info["my_gain"], "theirGain": info["their_gain"], "net": info["net"],
                "required": info["required"], "myVp": info["my_vp"], "oppVp": info["opp_vp"],
                "vetoed": info["vetoed"], "ok": info["ok"]}

    def current(self, game, s, weights, tp) -> dict | None:
        """The pending offer, judged for the seat that must answer it."""
        st = s.game.state
        if s.pending is not None or st.current_prompt != ActionPrompt.DECIDE_TRADE:
            return None
        trade = st.current_trade
        offerer = st.colors[trade[10]]
        responder = st.current_color()
        if responder == offerer:
            return None
        _, info = evaluate_trade(s.game, responder, offerer, list(trade[5:10]), list(trade[:5]),
                                 weights, tp)
        out = {"responder": st.color_to_index[responder], "offerer": trade[10],
               "give": list(trade[5:10]), "get": list(trade[:5])}
        out.update(self._info(info))
        return out

    def decisions(self, session, weights, tp, count: int) -> list[dict]:
        """Replay the log once and re-judge the last ``count`` trade steps."""
        game = session.game
        wanted = [i for i, step in enumerate(session.steps)
                  if step.player >= 0 and kind(str(step.action)) in TRADE_KINDS][-count * 4:]
        if not wanted:
            return []
        s = game.initial_state()
        out: list[dict] = []
        last = wanted[-1]
        wanted_set = set(wanted)
        for i, step in enumerate(session.steps[: last + 1]):
            if i in wanted_set:
                d = self._judge(game, s, step, weights, tp)
                if d is not None:
                    d["step"] = i
                    out.append(d)
            game.move(s, step.action)
        return out[-count:]

    def _judge(self, game, s, step, weights, tp) -> dict | None:
        st = s.game.state
        code = str(step.action)
        k = kind(code)
        actor = step.player
        color = st.colors[actor]
        names = [game.seat_label(i) for i in range(game.num_players)]
        base = {"actor": actor, "actorName": names[actor], "actual": code, "reasoning": None}
        if k == "OFFER":
            give, get = (list(map(int, part.split(","))) for part in code.split(":")[1].split(">"))
            best = None
            for seat, other in enumerate(st.colors):
                if other == color:
                    continue
                _, info = evaluate_trade(s.game, color, other, give, get, weights, tp)
                if best is None or (info["ok"], info["net"]) > (best[1]["ok"], best[1]["net"]):
                    best = (seat, info)
            seat, info = best
            base.update(kind="offer", give=give, get=get, **{"with": seat}, withName=names[seat],
                        reasoning=self._info(info), verdict="ok" if info["ok"] else "decline")
        elif k in ("ACCEPT", "REJECT"):
            trade = st.current_trade
            offerer = st.colors[trade[10]]
            if offerer == color:
                return None                                  # the engine's automatic self-answer
            give, get = list(trade[5:10]), list(trade[:5])
            _, info = evaluate_trade(s.game, color, offerer, give, get, weights, tp)
            base.update(kind="answer", give=give, get=get, **{"with": trade[10]},
                        withName=names[trade[10]], reasoning=self._info(info),
                        verdict="accept" if info["ok"] else ("veto" if info["vetoed"] else "decline"))
        elif k == "CONFIRM":
            trade = st.current_trade
            partner = st.color_to_index[Color[code.split(":")[1]]]
            give, get = list(trade[:5]), list(trade[5:10])
            _, info = evaluate_trade(s.game, color, st.colors[partner], give, get, weights, tp)
            base.update(kind="deal", give=give, get=get, **{"with": partner}, withName=names[partner],
                        reasoning=self._info(info), verdict="ok" if info["ok"] else "decline")
        else:
            trade = st.current_trade
            base.update(kind="cancel", give=list(trade[:5]), get=list(trade[5:10]),
                        verdict="cancel")
        return base
