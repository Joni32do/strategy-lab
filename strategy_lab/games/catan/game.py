"""Settlers of Catan on the catanatron engine.

Nothing here re-implements a Catan rule. The vendored ``catanatron`` engine
owns the rules (move generation, building, longest road, robber, trading).
This adapter makes it a replayable :class:`~strategy_lab.core.game.Game`.

Replayable randomness
---------------------
Catanatron draws from Python's global ``random``: the board, the turn order,
the dice, the stolen card and the development card. The lab needs every game
to replay from its action log, so all of that becomes *chance nodes*:

* **Board seed** (the very first node): ``sample_chance`` returns a 31-bit
  seed and ``chance_outcomes`` raises ``NotImplementedError`` (seed-as-outcome).
  The seed builds the engine game with the global RNG saved and restored
  around it, so the lab never disturbs anyone else's random numbers.
* **Dice**: choosing ``ROLL`` opens a chance node over the 11 sums 2..12
  (probabilities 1/36 ... 6/36). The sum is replayed into the engine with an
  ``ActionRecord`` (the engine's own replay hook).
* **Stealing**: moving the robber onto a victim opens a chance node over the
  victim's cards (probability proportional to the count).
* **Development card**: buying one opens a chance node over the cards left in
  the deck.

After the seed node the engine never consults ``random`` again. (Catanatron
*bots* do, to break ties: the policy wrapper seeds the global RNG from the
session's rng for the duration of one decision.)

Seats
-----
Seat 0..n-1 are Red, Blue, Orange, White in turn order, so seat 0 always opens
(the engine's random turn order is replaced by this fixed one right after the
board is built). Param ``players`` (2 to 4) sets the number of seats.

Hidden information
------------------
Hands and development cards are private; hand *sizes* and played knights are
public. ``scene`` shows the viewer's own hand, other seats only as counts, and
public victory points (the viewer sees their own hidden VP cards). A spectator
(``viewer is None``) sees everything.

Domestic trading
----------------
Catanatron lets a player propose any trade outside its list of playable
actions. The lab turns this into ordinary legal actions: after rolling, a seat
may open **one** offer per turn, giving 1 or 2 cards of one resource it holds
for 1 card of another. The others answer ``ACCEPT`` or ``REJECT``, then the
offerer picks ``CONFIRM:<color>`` or ``CANCEL``. (Catanatron re-asks the
offerer about their own offer when they are not seated first. The adapter
answers that pseudo-decision with ``REJECT`` automatically.)

Custom scene part ``hex``
-------------------------
::

    {"view": "hex", "width": 98.6, "height": 92.0, "size": 10.0,
     "tiles": [{"id": 0, "cx": 49.3, "cy": 46.0, "resource": "WOOD" | null (desert),
                "number": 5 | null, "robber": false,
                "points": [[x, y] x 6],                  # corners, north first, clockwise
                "nodes": [n x 6],                        # node ids of those corners (docks)
                "action": "ROBBER:0,0,0:-" | absent,     # click to move the robber here
                "actions": [{"action": ..., "label": "steal from Blue"}]  # several victims
               }, ...],                                  # 19 tiles
     "edges": [{"a": 3, "b": 4, "x1": .., "y1": .., "x2": .., "y2": ..,
                "owner": seat | absent, "action": "ROAD:3-4" | absent}],
     "nodes": [{"id": 12, "x": .., "y": .., "owner": seat | absent,
                "kind": "settlement" | "city" | absent,
                "action": "SETTLEMENT:12" | "CITY:12" | absent}],
     "ports": [{"nodes": [a, b], "x": .., "y": .., "resource": "WOOD" | null, "ratio": 2 | 3}]}

``edges`` lists only roads and clickable edges, ``nodes`` only buildings and
clickable nodes (positions are in the same plane as the tiles). ``owner`` is a
seat index (palette ``--p0..``). Everything else (rolling, bank trades, offers,
development cards) is a stock ``scene.buttons`` part, hands and victory points
are ``scene.kv`` panels.
"""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from catanatron.game import TURNS_LIMIT, Game as EngineGame
from catanatron.models.actions import generate_playable_actions
from catanatron.models.enums import (
    DEVELOPMENT_CARDS, RESOURCES, Action, ActionPrompt, ActionRecord, ActionType as AT)
from catanatron.models.player import Color, Player as EnginePlayer, RandomPlayer
from catanatron.players.value import ValueFunctionPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer
from catanatron.state_functions import (
    get_actual_victory_points, get_dev_cards_in_hand, get_largest_army,
    get_longest_road_length, get_played_dev_cards, get_player_freqdeck,
    get_visible_victory_points, player_has_rolled, player_num_resource_cards)

from strategy_lab.core import (
    CHANCE, Bot, Challenge, Game, Model, Param, Policy, Rulebook, avoid, pick, scene)
from strategy_lab.core.game import Action as LabAction
from strategy_lab.games.catan import board as geo
from strategy_lab.games.catan.actions import (
    cards_text, encode, kind, offer_action, sort_key)
from strategy_lab.games.catan.policy import (
    MetricWeights, StrategicTradingPlayer, TradeParams, position_strength)

SEED_LIMIT = 2 ** 31
COLORS = (Color.RED, Color.BLUE, Color.ORANGE, Color.WHITE)
#: Sum of two dice -> a fixed pair of faces (only the sum matters to the rules).
DICE_PAIR = {s: (min(6, s - 1), s - min(6, s - 1)) for s in range(2, 13)}
DICE_WAYS = {s: 6 - abs(s - 7) for s in range(2, 13)}
DEV_NAMES = {"KNIGHT": "knight", "YEAR_OF_PLENTY": "year of plenty", "MONOPOLY": "monopoly",
             "ROAD_BUILDING": "road building", "VICTORY_POINT": "victory point"}


@contextmanager
def seeded_global_random(seed: int):
    """Run a block with ``random`` seeded, then restore the previous global state."""
    saved = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(saved)


@dataclass
class CatanState:
    """A game of Catan between decisions.

    ``game`` is the engine's :class:`catanatron.game.Game` (``None`` until the
    board seed is drawn). ``pending`` is a decision whose random result is not
    drawn yet: ``("roll" | "steal" | "dev", engine Action)``.
    """

    game: EngineGame | None = None
    seed: int | None = None
    pending: tuple[str, Action] | None = None
    #: Offers opened in the current turn (the lab allows one).
    offers: int = 0
    steps: int = 0
    digest: str = ""
    #: ``{action string: engine Action}`` for the current decision, built lazily.
    options: dict | None = field(default=None, repr=False, compare=False)


def new_engine_game(seed: int, n: int, vps_to_win: int) -> EngineGame:
    """Build a game for ``n`` seats with the global RNG saved and restored."""
    players = [EnginePlayer(c) for c in COLORS[:n]]
    with seeded_global_random(seed):
        game = EngineGame(players, seed=seed, vps_to_win=vps_to_win)
    st = game.state
    st.players = players                       # fixed seating: seat i is COLORS[i]
    st.colors = tuple(COLORS[:n])
    st.color_to_index = {c: i for i, c in enumerate(st.colors)}
    game.playable_actions = generate_playable_actions(st)
    return game


class CatanPolicy(Policy):
    """Wraps a catanatron :class:`Player` (one instance per seat) as a lab policy.

    The engine player decides on the engine's playable actions. The wrapper
    maps its answer to the lab's action string and falls back to the first
    legal action if the engine player returns something the lab does not offer
    (for example a second trade offer in one turn). Catanatron bots break ties
    with the global ``random``: it is seeded from ``rng`` for one decision.
    """

    def __init__(self, factory, name: str):
        self.factory = factory
        self.name = name
        self._players: dict[int, EnginePlayer] = {}

    def player(self, game: "Catan", s: CatanState, seat: int) -> EnginePlayer:
        if seat not in self._players:
            self._players[seat] = self.factory(s.game.state.colors[seat])
        return self._players[seat]

    def act(self, game, s, player, rng):
        options = game.options(s)
        if len(options) == 1:
            return next(iter(options))
        bot = self.player(game, s, player)
        if hasattr(bot, "allow_offers"):
            bot.allow_offers = game.offer_allowed(s)
        with seeded_global_random(rng.randrange(SEED_LIMIT)):
            choice = bot.decide(s.game, list(s.game.playable_actions))
        code = encode(choice)
        return code if code in options else next(iter(options))

    def trace(self, game, s, player):
        bot = self.player(game, s, player)
        with seeded_global_random(20260710):
            self.act(game, s, player, random.Random(20260710))
        return {"policy": self.name, "explanation": getattr(bot, "last_explanation", None)}


class Catan(Game):
    id = "catan"
    name = "Catan"
    icon = "hexagon"
    tagline = "Build, trade and block. Whom do you help when the leader is one road away?"
    chapter = "society"
    order = 10
    concepts = ("multi-agent", "negotiation", "expected-value", "risk", "imperfect-information",
                "heuristic")
    seat_names = ("Red", "Blue", "Orange", "White")
    perfect_information = False
    stochastic = True
    #: A long game of four takes about 1500 steps; 4000 ends runaways as a draw.
    max_steps = 4000
    #: Conformance playouts of every bot and card are capped at this many steps.
    conformance_steps = 150

    family_id = "catanatron"
    family_name = "Catanatron engine"
    family_blurb = ("Games that run on the catanatron simulator: full rules from the "
                    "engine, hidden hands, and a seat count you can change.")

    params = {
        "players": Param(4, "Players", "Seats at the table (2 to 4).", min=2, max=4),
        "vps_to_win": Param(10, "Victory points to win", "The official game is played to 10.",
                            min=3, max=15),
        "trading": Param(True, "Player trades",
                         "Allow one trade offer per turn between players."),
    }

    rulebook = Rulebook(
        summary="Collect resources from the tiles around your settlements, build roads, "
                "settlements and cities, and be the first to 10 victory points.",
        steps=(
            ("Setup", "In turn order, then back again in reverse order, each player places "
                      "a settlement and an adjoining road. The second settlement pays one "
                      "card from each tile around it."),
            ("Your turn", "Roll two dice. Every tile with that number pays one card to each "
                          "settlement (two to each city) next to it. Then trade and build in "
                          "any order, and end the turn."),
            ("A 7", "Nobody collects. Players with more than 7 cards discard half. You move "
                    "the robber to another tile: it blocks that tile and you steal one card "
                    "from a player with a building there."),
            ("Building", "Road: 1 wood + 1 brick. Settlement: wood, brick, sheep, wheat "
                         "(not next to another building). City: 2 wheat + 3 ore on a "
                         "settlement. Development card: sheep + wheat + ore."),
            ("Trading", "Trade with the bank 4:1, or 3:1 and 2:1 with a port. Offer cards to "
                        "the other players: they accept or decline."),
            ("Points", "Settlement 1, city 2, longest road (5 or more) 2, largest army (3 or "
                       "more knights) 2, victory point cards 1 each."),
        ),
        extra=(
            ("Engine", "All rules come from the catanatron simulator, not from the lab. "
                       "Rules differences, if any, belong to catanatron: "
                       "https://github.com/bcollazo/catanatron"),
            ("Fixed seating", "Seat 0 (Red) always starts. The lab replaces catanatron's "
                              "random turn order so that seats are stable."),
            ("One offer per turn", "A player may open one trade offer per turn, offering 1 "
                                   "or 2 cards of one resource for 1 card of another. The "
                                   "official rules allow any number of offers and swaps."),
            ("No partner restriction", "Offers go to all other players at once."),
        ),
        source="https://www.catan.com/understand-catan/game-rules",
    )

    models = (
        Model("board-hands", "Board + your hand", False,
              state="settlements, cities, roads, robber, your cards, public points",
              size="more than 10^100 positions",
              actions="up to about 60 per decision: build, trade, play a card, end the turn",
              reward="+1 for the winner, -1 for the others, at the end (very sparse)",
              note="Not Markov: the robber, the bank and the other hands change what is "
                   "possible, and the opponents' cards are hidden."),
        Model("strength", "Position strength of each player", "approx",
              state="one number per player in [0, 1]: points, production and room to expand",
              size="a handful of numbers",
              actions="the same legal actions, ranked by how they change the strengths",
              reward="the gain in my strength minus lambda times the gain of my rival",
              note="A hand-made summary. It keeps what the trade rule needs and drops the "
                   "rest. The trade lens shows how the choices of lambda follow from it."),
        Model("full-public", "Public board + hand sizes + all of your information", True,
              state="everything on the table, your hand and development cards, how many "
                    "cards each rival holds, the bank, and who has the longest road and "
                    "largest army",
              actions="every legal action",
              transition="dice, steals and card draws are chance; the rivals' decisions "
                         "depend on hands you cannot see",
              reward="+1 / -1 at the end, or shaped by victory points",
              note="The honest formulation, and far too large to learn from scratch. "
                   "Good bots mix search with a value function of the strength above."),
    )

    bots = (
        Bot("random", "Randy Rookie", "Plays a random legal move. Builds roads to nowhere.",
            1, policy="random_policy", icon="dice"),
        Bot("wanda", "Wanda Weighted", "Random, but cities beat settlements beat "
            "development cards beat everything else.", 2, policy="weighted_policy",
            icon="sparkle"),
        Bot("vera", "Vera Value", "Scores every move with a value function (points, "
            "production, reach) and plays the best. Never trades.", 3,
            policy="value_policy", icon="chart"),
        Bot("tina", "Tina the Trader", "Vera's brain plus a trading brain: she weighs a "
            "rival's gain by how close the rival is to winning, and refuses to feed a "
            "leader.", 4, policy="trader_policy", icon="handshake"),
        Bot("blake", "Blake the Blocker", "Tina, but she also prefers builds that cut "
            "rivals off from new building spots.", 4, policy="blocker_policy", icon="barrier"),
    )

    challenges = (
        Challenge("finish", "Watch or play a game to the end", "finish"),
        Challenge("trade", "Open the trading lens", "lens", 1, lens="trade"),
        Challenge("beat-wanda", "Win against Wanda Weighted", "win", 2, bot="wanda"),
        Challenge("beat-vera", "Win against Vera Value", "win", 3, bot="vera"),
        Challenge("beat-tina", "Win against Tina the Trader", "win", 3, bot="tina"),
    )

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.num_players = int(self.p["players"])

    # ======================================================================= #
    # Rules
    # ======================================================================= #
    def initial_state(self) -> CatanState:
        return CatanState()

    def copy_state(self, s: CatanState) -> CatanState:
        return CatanState(game=s.game.copy() if s.game is not None else None, seed=s.seed,
                          pending=s.pending, offers=s.offers, steps=s.steps, digest=s.digest)

    def current_player(self, s: CatanState) -> int:
        if s.game is None or s.pending is not None:
            return CHANCE
        return s.game.state.current_player_index

    def is_terminal(self, s: CatanState) -> bool:
        if s.game is None:
            return False
        return s.game.winning_color() is not None or s.game.state.num_turns >= TURNS_LIMIT

    def winner(self, s: CatanState) -> int | None:
        color = s.game.winning_color() if s.game is not None else None
        return None if color is None else s.game.state.color_to_index[color]

    def key(self, s: CatanState) -> str:
        return f"{s.seed}:{s.steps}:{s.digest}"

    # -- legal actions ------------------------------------------------------ #
    def offer_allowed(self, s: CatanState) -> bool:
        """May the seat to move open a trade offer now?"""
        st = s.game.state
        color = st.current_color()
        return (self.p["trading"] and s.pending is None and s.offers == 0
                and st.current_prompt == ActionPrompt.PLAY_TURN
                and player_has_rolled(st, color) and not st.is_resolving_trade
                and not st.is_road_building and sum(get_player_freqdeck(st, color)) > 0)

    def offers_for(self, s: CatanState) -> list[Action]:
        """Offers of 1 or 2 cards of one held resource for 1 of another."""
        color = s.game.state.current_color()
        hand = get_player_freqdeck(s.game.state, color)
        out = []
        for g in range(5):
            for n in (1, 2):
                if hand[g] < n:
                    continue
                for w in range(5):
                    if w != g:
                        give = tuple(n if i == g else 0 for i in range(5))
                        get = tuple(1 if i == w else 0 for i in range(5))
                        out.append(offer_action(color, give, get))
        return out

    def options(self, s: CatanState) -> dict[str, Action]:
        """``{action string: engine Action}`` for the seat to move (cached on the state)."""
        if s.options is None:
            st = s.game.state
            actions = list(s.game.playable_actions)
            if st.current_prompt == ActionPrompt.DECIDE_TRADE:
                offerer = st.colors[st.current_trade[10]]
                if st.current_color() == offerer:      # engine quirk: answer the own offer
                    actions = [a for a in actions if a.action_type == AT.REJECT_TRADE]
            elif self.offer_allowed(s):
                actions += self.offers_for(s)
            actions.sort(key=sort_key)
            s.options = {encode(a): a for a in actions}
        return s.options

    def legal_actions(self, s: CatanState) -> list[LabAction]:
        return list(self.options(s))

    def chance_outcomes(self, s: CatanState) -> list[tuple[LabAction, float]]:
        if s.game is None:
            raise NotImplementedError("the board seed cannot be enumerated")
        kind_, act = s.pending
        st = s.game.state
        if kind_ == "roll":
            return [(n, DICE_WAYS[n] / 36) for n in range(2, 13)]
        if kind_ == "steal":
            hand = get_player_freqdeck(st, act.value[1])
            total = sum(hand)
            return [(RESOURCES[i], n / total) for i, n in enumerate(hand) if n]
        deck = Counter(st.development_listdeck)
        total = sum(deck.values())
        return [(c, deck[c] / total) for c in DEVELOPMENT_CARDS if deck[c]]

    def sample_chance(self, s: CatanState, rng) -> LabAction:
        if s.game is None:
            return rng.randrange(SEED_LIMIT)
        return super().sample_chance(s, rng)

    def move(self, s: CatanState, a: LabAction) -> None:
        s.steps += 1
        s.digest = hashlib.md5(f"{s.digest}|{a}".encode()).hexdigest()[:12]
        if s.game is None:
            s.seed = int(a)
            s.game = new_engine_game(s.seed, self.num_players, self.p["vps_to_win"])
        elif s.pending is not None:
            self._resolve_chance(s, a)
        else:
            self._decide(s, str(a))
        s.options = None                        # the decision changed what is legal

    def _resolve_chance(self, s: CatanState, outcome: LabAction) -> None:
        kind_, act = s.pending
        s.pending = None
        result: Any = DICE_PAIR[int(outcome)] if kind_ == "roll" else str(outcome)
        s.game.execute(act, validate_action=False, action_record=ActionRecord(act, result))

    def _decide(self, s: CatanState, code: str) -> None:
        act = self.options(s)[code]
        t = act.action_type
        if t == AT.ROLL:
            s.pending = ("roll", act)
        elif t == AT.BUY_DEVELOPMENT_CARD:
            s.pending = ("dev", act)
        elif t == AT.MOVE_ROBBER and act.value[1] is not None:
            s.pending = ("steal", act)
        else:
            s.game.execute(act)
            if t == AT.END_TURN:
                s.offers = 0
            elif t == AT.OFFER_TRADE:
                s.offers += 1

    # ======================================================================= #
    # Knowledge
    # ======================================================================= #
    def observation(self, s: CatanState, player: int) -> str:
        """What ``player`` knows: own cards, the public board and rivals' hand sizes."""
        if s.game is None:
            return "no board yet"
        st, b = s.game.state, s.game.state.board
        color = st.colors[player]
        parts = [f"you={color.value}", f"hand={get_player_freqdeck(st, color)}",
                 f"dev={[get_dev_cards_in_hand(st, color, c) for c in DEVELOPMENT_CARDS]}",
                 f"robber={b.robber_coordinate}", f"turn={st.num_turns}",
                 f"prompt={st.current_prompt.value}"]
        for i, c in enumerate(st.colors):
            parts.append(f"{c.value}:vp={get_visible_victory_points(st, c)},"
                         f"cards={player_num_resource_cards(st, c)},"
                         f"knights={get_played_dev_cards(st, c, 'KNIGHT')}")
        parts.append("buildings=" + ",".join(f"{n}{'C' if t == 'CITY' else 'S'}{c.value[0]}"
                                              for n, (c, t) in sorted(b.buildings.items())))
        parts.append("roads=" + ",".join(f"{a}-{z}{c.value[0]}"
                                          for (a, z), c in sorted(b.roads.items()) if a < z))
        return "|".join(parts)

    def heuristic(self, s: CatanState, player: int) -> float:
        """Own position strength minus the best rival's, in ``[-1, 1]``."""
        weights = MetricWeights()
        st = s.game.state
        mine = position_strength(s.game, st.colors[player], weights)[0]
        best = max(position_strength(s.game, c, weights)[0]
                   for i, c in enumerate(st.colors) if i != player)
        return mine - best

    # ======================================================================= #
    # Hidden information in the move log
    # ======================================================================= #
    def privacy(self, s: CatanState, a: LabAction, player: int):
        if player == CHANCE and s.pending is not None:
            kind_, act = s.pending
            st = s.game.state
            seat = st.color_to_index[act.color]
            if kind_ == "dev":
                return (seat,)
            if kind_ == "steal":
                return (seat, st.color_to_index[act.value[1]])
        elif player >= 0 and kind(str(a)) == "DISCARD":
            return (player,)
        return None

    def describe_hidden(self, s: CatanState, a: LabAction, player: int) -> str:
        if player == CHANCE:
            kind_, _ = s.pending
            return "draws a development card" if kind_ == "dev" else "takes a card"
        return "discards a card"

    # ======================================================================= #
    # Presentation
    # ======================================================================= #
    def tile_text(self, s: CatanState, coord: tuple[int, int, int]) -> str:
        tile = s.game.state.board.map.land_tiles[coord]
        if tile.resource is None:
            return "the desert"
        return f"{tile.resource.lower()} {tile.number}"

    def label_of(self, s: CatanState, code: str) -> str:
        """Button label of an action string."""
        k, _, rest = code.partition(":")
        if k == "ROLL":
            return "Roll the dice"
        if k == "END_TURN":
            return "End turn"
        if k == "BUY_DEV":
            return "Buy a development card"
        if k == "SETTLEMENT":
            return f"Settlement on node {rest}"
        if k == "CITY":
            return f"City on node {rest}"
        if k == "ROAD":
            return f"Road {rest}"
        if k == "ROBBER":
            coord, victim = rest.split(":")
            where = self.tile_text(s, tuple(int(x) for x in coord.split(",")))
            return f"Robber to {where}" + ("" if victim == "-" else f", steal from {victim.title()}")
        if k == "DISCARD":
            return f"Discard {rest.lower()}"
        if k == "KNIGHT":
            return "Play a knight"
        if k == "ROAD_BUILDING":
            return "Play road building"
        if k == "MONOPOLY":
            return f"Monopoly on {rest.lower()}"
        if k == "YOP":
            return "Year of plenty: " + " and ".join(r.lower() for r in rest.split("+"))
        if k == "BANK":
            give, get = rest.split(">")
            res, n = give.split("*")
            return f"Bank: {n} {res.lower()} for 1 {get.lower()}"
        if k == "OFFER":
            give, get = rest.split(">")
            return (f"Offer {cards_text([int(x) for x in give.split(',')])} for "
                    f"{cards_text([int(x) for x in get.split(',')])}")
        if k == "ACCEPT":
            return "Accept"
        if k == "REJECT":
            return "Decline"
        if k == "CONFIRM":
            return f"Trade with {rest.title()}"
        return "Cancel the offer" if k == "CANCEL" else code

    def action_label(self, s: CatanState, a: LabAction) -> str:
        if s.game is None:
            return f"board {a}"
        if s.pending is not None:
            kind_ = s.pending[0]
            if kind_ == "dev":
                return DEV_NAMES[str(a)]
            return str(a) if kind_ == "roll" else str(a).lower()
        return self.label_of(s, str(a))

    def describe(self, s: CatanState, a: LabAction, player: int) -> str:
        code = str(a)
        k, _, rest = code.partition(":")
        text = {"ROLL": "rolls the dice", "END_TURN": "ends the turn",
                "BUY_DEV": "buys a development card", "KNIGHT": "plays a knight",
                "ROAD_BUILDING": "plays road building", "ACCEPT": "accepts the offer",
                "REJECT": "declines the offer", "CANCEL": "calls the offer off"}.get(k)
        if text:
            return text
        if k in ("SETTLEMENT", "CITY", "ROAD"):
            return {"SETTLEMENT": "builds a settlement", "CITY": "builds a city",
                    "ROAD": "builds a road"}[k]
        if k == "ROBBER":
            label = self.label_of(s, code)
            return "moves the " + label[:1].lower() + label[1:].replace(", steal", " and steals")
        if k == "DISCARD":
            return f"discards {rest.lower()}"
        if k == "CONFIRM":
            return f"closes the deal with {rest.title()}"
        label = self.label_of(s, code)
        return label[:1].lower() + label[1:] if k in ("BANK", "OFFER", "MONOPOLY", "YOP") else label

    def describe_chance(self, s: CatanState, a: LabAction) -> str:
        if s.game is None:
            return f"shuffles the board (seed {a})"
        kind_, act = s.pending
        if kind_ == "roll":
            return f"the dice show {a}"
        if kind_ == "steal":
            return f"takes a {str(a).lower()} from {act.value[1].value.title()}"
        return f"draws a {DEV_NAMES[str(a)]} card"

    def status(self, s: CatanState, viewer: int | None) -> str:
        if s.game is None:
            return "Shuffling the board..."
        st = s.game.state
        if self.is_terminal(s):
            w = self.winner(s)
            if w is None:
                return "Game over: nobody won in time"
            return "Game over: you won" if w == viewer else f"Game over: {self.seat_label(w)} won"
        if s.pending is not None:
            return {"roll": "Rolling the dice...", "steal": "Stealing a card...",
                    "dev": "Drawing a development card..."}[s.pending[0]]
        p = st.current_player_index
        who = "You" if p == viewer else self.seat_label(p)
        prompt = st.current_prompt
        text = {
            ActionPrompt.BUILD_INITIAL_SETTLEMENT: "place a settlement",
            ActionPrompt.BUILD_INITIAL_ROAD: "place a road next to it",
            ActionPrompt.MOVE_ROBBER: "move the robber",
            ActionPrompt.DISCARD: f"discard {st.discard_counts[p]} card(s)",
            ActionPrompt.DECIDE_TRADE: "answer the trade offer",
            ActionPrompt.DECIDE_ACCEPTEES: "pick who to trade with",
        }.get(prompt)
        if text is None:
            if st.is_road_building:
                text = f"build a free road ({st.free_roads_available} left)"
            elif not player_has_rolled(st, st.colors[p]):
                text = "roll the dice"
            else:
                text = "build, trade or end the turn"
        return f"{who}: {text}" if p == viewer else f"{who} to {text}"

    # -- scene --------------------------------------------------------------- #
    def hand_text(self, s: CatanState, seat: int, viewer: int | None) -> str:
        st = s.game.state
        color = st.colors[seat]
        if viewer is None or viewer == seat:
            return cards_text(get_player_freqdeck(st, color))
        return f"{player_num_resource_cards(st, color)} cards"

    def seat_panel(self, s: CatanState, seat: int, viewer: int | None) -> dict:
        st = s.game.state
        color = st.colors[seat]
        own = viewer is None or viewer == seat
        vp = get_actual_victory_points(st, color) if own else get_visible_victory_points(st, color)
        devs = sum(get_dev_cards_in_hand(st, color, c) for c in DEVELOPMENT_CARDS)
        strength = position_strength(s.game, color, MetricWeights())[0]
        items = [("Victory points", f"{vp}" + ("" if own else " (public)")),
                 ("Cards", self.hand_text(s, seat, viewer)),
                 ("Development cards", f"{devs}" + (
                     f" ({', '.join(DEV_NAMES[c] + ' ' + str(get_dev_cards_in_hand(st, color, c)) for c in DEVELOPMENT_CARDS if get_dev_cards_in_hand(st, color, c))})"
                     if own and devs else "")),
                 ("Knights played", get_played_dev_cards(st, color, "KNIGHT")),
                 ("Longest road", get_longest_road_length(st, color)),
                 ("Strength", f"{strength:.2f}")]
        return scene.kv(items, caption=self.seat_label(seat), owner=seat)

    def board_part(self, s: CatanState, viewer: int | None) -> dict:
        st = s.game.state
        board = st.board
        mover = st.current_player_index
        options = (self.options(s) if not self.is_terminal(s) and s.pending is None
                   and viewer == mover else {})
        node_action: dict[int, str] = {}
        edge_action: dict[tuple, str] = {}
        tile_actions: dict[tuple, list[dict]] = {}
        for code in options:
            k, _, rest = code.partition(":")
            if k in ("SETTLEMENT", "CITY"):
                node_action[int(rest)] = code
            elif k == "ROAD":
                a, b = rest.split("-")
                edge_action[(int(a), int(b))] = code
            elif k == "ROBBER":
                coord, victim = rest.split(":")
                tile_actions.setdefault(tuple(int(x) for x in coord.split(",")), []).append(
                    {"action": code, "label": "no one to steal from" if victim == "-"
                     else f"steal from {victim.title()}"})
        tiles = []
        for tg in geo.TILES.values():
            tile = board.map.land_tiles[tg.coord]
            entry = {"id": tg.id, "cx": tg.cx, "cy": tg.cy, "resource": tile.resource,
                     "number": tile.number, "robber": board.robber_coordinate == tg.coord,
                     "points": [list(geo.NODES[n]) for n in tg.nodes],
                     "nodes": list(tg.nodes)}
            acts = tile_actions.get(tg.coord)
            if acts:
                entry["action"] = acts[0]["action"] if len(acts) == 1 else None
                entry["actions"] = acts
            tiles.append({k: v for k, v in entry.items() if v is not None})
        roads = {tuple(sorted(e)): c for e, c in board.roads.items()}
        edges = []
        for a, b in geo.EDGES:
            owner = roads.get((a, b))
            if owner is None and (a, b) not in edge_action:
                continue
            e = {"a": a, "b": b, "x1": geo.NODES[a][0], "y1": geo.NODES[a][1],
                 "x2": geo.NODES[b][0], "y2": geo.NODES[b][1]}
            if owner is not None:
                e["owner"] = st.color_to_index[owner]
            if (a, b) in edge_action:
                e["action"] = edge_action[(a, b)]
            edges.append(e)
        nodes = []
        for n in sorted(geo.NODES):
            building = board.buildings.get(n)
            if building is None and n not in node_action:
                continue
            e = {"id": n, "x": geo.NODES[n][0], "y": geo.NODES[n][1]}
            if building is not None:
                e["owner"] = st.color_to_index[building[0]]
                e["kind"] = "city" if building[1] == "CITY" else "settlement"
            if n in node_action:
                e["action"] = node_action[n]
            nodes.append(e)
        ports = []
        for pg in geo.PORTS.values():
            resource = board.map.ports_by_id[pg.id].resource
            ports.append({"nodes": list(pg.nodes), "x": pg.x, "y": pg.y,
                          "resource": resource, "ratio": 3 if resource is None else 2})
        return scene.custom("hex", width=geo.WIDTH, height=geo.HEIGHT, size=geo.SIZE,
                            tiles=tiles, edges=edges, nodes=nodes, ports=ports)

    def button_groups(self, s: CatanState, viewer: int | None) -> list[dict]:
        """Actions that are not on the board, grouped into button rows."""
        if self.is_terminal(s) or s.pending is not None or viewer != s.game.state.current_player_index:
            return []
        groups: dict[str, list[tuple[str, str]]] = {}
        names = {"ROLL": "Turn", "END_TURN": "Turn", "BUY_DEV": "Development cards",
                 "KNIGHT": "Development cards", "ROAD_BUILDING": "Development cards",
                 "MONOPOLY": "Play a development card", "YOP": "Play a development card",
                 "BANK": "Trade with the bank", "OFFER": "Offer a trade to the others",
                 "DISCARD": "Discard", "ACCEPT": "Trade offer", "REJECT": "Trade offer",
                 "CONFIRM": "Pick a partner", "CANCEL": "Pick a partner"}
        for code in self.options(s):
            k = kind(code)
            if k in ("SETTLEMENT", "CITY", "ROAD", "ROBBER"):
                continue
            groups.setdefault(names[k], []).append((code, self.label_of(s, code)))
        return [scene.buttons(choices, caption=caption) for caption, choices in groups.items()]

    def scene(self, s: CatanState, viewer: int | None) -> dict:
        if s.game is None:
            return scene.scene([scene.text("Shuffling the board...")], status=self.status(s, viewer))
        st = s.game.state
        parts = [self.board_part(s, viewer)]
        if s.pending is None and not self.is_terminal(s) and st.current_prompt == ActionPrompt.DECIDE_TRADE:
            t = st.current_trade
            offerer = st.colors[t[10]]
            parts.append(scene.kv([("From", offerer.value.title()),
                                   ("Offers you", cards_text(t[:5])),
                                   ("Asks in return", cards_text(t[5:10]))],
                                  caption="Trade offer"))
        parts.extend(self.button_groups(s, viewer))
        parts.extend(self.seat_panel(s, seat, viewer) for seat in range(self.num_players))
        players = [scene.player(self.seat_label(i),
                                score=(get_actual_victory_points(st, c) if viewer in (None, i)
                                       else get_visible_victory_points(st, c)),
                                sub=self.hand_text(s, i, viewer),
                                active=(not self.is_terminal(s) and s.pending is None
                                        and st.current_player_index == i), owner=i)
                   for i, c in enumerate(st.colors)]
        return scene.scene(parts, players=players, layout="split", status=self.status(s, viewer))

    # ======================================================================= #
    # Bots
    # ======================================================================= #
    def random_policy(self) -> Policy:
        return CatanPolicy(RandomPlayer, "Randy Rookie")

    def weighted_policy(self) -> Policy:
        return CatanPolicy(WeightedRandomPlayer, "Wanda Weighted")

    def value_policy(self) -> Policy:
        return CatanPolicy(ValueFunctionPlayer, "Vera Value")

    def trader_policy(self) -> Policy:
        return CatanPolicy(StrategicTradingPlayer, "Tina the Trader")

    def blocker_policy(self) -> Policy:
        return CatanPolicy(lambda color: StrategicTradingPlayer(
            color, weights=MetricWeights(block_weight=1.0)), "Blake the Blocker")

    # ======================================================================= #
    # Rule cards
    # ======================================================================= #
    @staticmethod
    def _first(candidates, prefix: str):
        return next((c for c in candidates if c.startswith(prefix)), None)

    @pick("city", "Upgrade to a city", "A city pays double. Build one whenever you can.", "castle")
    def card_city(self, s, candidates, player, rng):
        return self._first(candidates, "CITY:")

    @pick("settlement", "Build a settlement", "More buildings, more points, more production.",
          "house")
    def card_settlement(self, s, candidates, player, rng):
        return self._first(candidates, "SETTLEMENT:")

    @pick("dev-card", "Buy a development card", "Knights, points and tricks for sheep, wheat "
          "and ore.", "sheet")
    def card_dev_card(self, s, candidates, player, rng):
        return self._first(candidates, "BUY_DEV")

    @pick("knight", "Play your knight", "Move the robber as soon as a knight is in hand.",
          "sword")
    def card_knight(self, s, candidates, player, rng):
        return self._first(candidates, "KNIGHT")

    @pick("block-leader", "Rob the leader",
          "Move the robber onto the tile of the player with the most public points and "
          "steal from them.", "target")
    def card_block_leader(self, s, candidates, player, rng):
        st = s.game.state
        best, best_vp = None, -1
        for c in candidates:
            if kind(c) != "ROBBER" or c.endswith(":-"):
                continue
            victim = Color[c.rsplit(":", 1)[1]]
            vp = get_visible_victory_points(st, victim)
            if vp > best_vp:
                best, best_vp = c, vp
        return best

    @avoid("no-offers", "No trade offers", "Never open a trade offer.", "barrier")
    def card_no_offers(self, s, action, player):
        return kind(action) == "OFFER"

    @avoid("no-bank", "No bank trades", "Keep your cards: no 4:1 bank swaps.", "shield")
    def card_no_bank(self, s, action, player):
        return kind(action) == "BANK"
