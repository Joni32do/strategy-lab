"""Monopoly: a two player duel on the classic 40 square board.

The dice turns run by themselves. Your policy answers the questions that
matter: buy it? build on it? pay your way out of jail? Dice rolls and card
draws are chance nodes, the decisions are the only actions.

Turn machine
------------
``settle`` runs the forced steps of a turn and stops at the next thing that
needs an outcome or a choice. The stages are:

``roll``    a chance node rolls the pair of dice (``"3-5"``, 21 outcomes)
``jailroll``a chance node rolls for doubles from jail
``card``    a chance node draws one of 8 equally likely cards
``jail``    decide: ``"pay"`` $50 now or ``"wait"`` and roll for doubles
``buy``     decide: ``"buy"`` the square you landed on or ``"skip"``
``build``   decide: ``"build:<square>"`` a house, or ``"done"``

Rules from the official game (linked in the rulebook): $1500 start, $200 for
reaching GO, a double gives another roll and a third double sends you to
jail, jail by Go To Jail / a card / three doubles, double rent on a complete
unimproved color group, railroad rent 25/50/100/200, utility rent 4x or 10x
the roll, building evenly.

Documented simplifications (also in the rulebook):

* no auctions (declining a purchase leaves the square unowned), no trading,
  no mortgages: a player who cannot pay is forced to sell houses and then
  properties to the bank at half price, and loses if that is not enough;
* at most 4 houses per street and no hotels, with an approximated rent curve
  of ``base rent x 1, 5, 15, 30, 40``;
* Chance and Community Chest are one compact deck of 8 equally likely cards
  that is drawn with replacement, and there is no Get Out of Jail Free card;
* income tax is a flat $200, as in the official short game;
* two players, the first seat starts, and after ``rounds`` turns each the
  richer player (cash, property prices and buildings at cost) wins.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Rulebook, avoid, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.dice import DiceState, RollAndMoveGame

# kinds: go prop rr util tax chance chest jail gotojail free
# (name, kind, group, price, base rent)
SQUARES = (
    ("GO", "go", 0, 0, 0),
    ("Mediterranean Ave", "prop", 0, 60, 2),
    ("Community Chest", "chest", 0, 0, 0),
    ("Baltic Ave", "prop", 0, 60, 4),
    ("Income Tax", "tax", 0, 200, 0),
    ("Reading Railroad", "rr", 0, 200, 0),
    ("Oriental Ave", "prop", 1, 100, 6),
    ("Chance", "chance", 0, 0, 0),
    ("Vermont Ave", "prop", 1, 100, 6),
    ("Connecticut Ave", "prop", 1, 120, 8),
    ("Jail - Just Visiting", "jail", 0, 0, 0),
    ("St. Charles Place", "prop", 2, 140, 10),
    ("Electric Company", "util", 0, 150, 0),
    ("States Ave", "prop", 2, 140, 10),
    ("Virginia Ave", "prop", 2, 160, 12),
    ("Pennsylvania Railroad", "rr", 0, 200, 0),
    ("St. James Place", "prop", 3, 180, 14),
    ("Community Chest", "chest", 0, 0, 0),
    ("Tennessee Ave", "prop", 3, 180, 14),
    ("New York Ave", "prop", 3, 200, 16),
    ("Free Parking", "free", 0, 0, 0),
    ("Kentucky Ave", "prop", 4, 220, 18),
    ("Chance", "chance", 0, 0, 0),
    ("Indiana Ave", "prop", 4, 220, 18),
    ("Illinois Ave", "prop", 4, 240, 20),
    ("B&O Railroad", "rr", 0, 200, 0),
    ("Atlantic Ave", "prop", 5, 260, 22),
    ("Ventnor Ave", "prop", 5, 260, 22),
    ("Water Works", "util", 0, 150, 0),
    ("Marvin Gardens", "prop", 5, 280, 24),
    ("Go To Jail", "gotojail", 0, 0, 0),
    ("Pacific Ave", "prop", 6, 300, 26),
    ("North Carolina Ave", "prop", 6, 300, 26),
    ("Community Chest", "chest", 0, 0, 0),
    ("Pennsylvania Ave", "prop", 6, 320, 28),
    ("Short Line Railroad", "rr", 0, 200, 0),
    ("Chance", "chance", 0, 0, 0),
    ("Park Place", "prop", 7, 350, 35),
    ("Luxury Tax", "tax", 0, 100, 0),
    ("Boardwalk", "prop", 7, 400, 50),
)
GROUP_TONES = ("brown", "lightblue", "pink", "orange", "red", "yellow", "green", "navy")
HOUSE_COST = (50, 50, 100, 100, 150, 150, 200, 200)
RENT_MULTIPLIER = (1, 5, 15, 30, 40)
MAX_HOUSES = 4
GROUPS: tuple[tuple[int, ...], ...] = tuple(
    tuple(i for i, sq in enumerate(SQUARES) if sq[1] == "prop" and sq[2] == g) for g in range(8))
RAILROADS = tuple(i for i, sq in enumerate(SQUARES) if sq[1] == "rr")
UTILITIES = tuple(i for i, sq in enumerate(SQUARES) if sq[1] == "util")
ICONS = {"go": "flag", "jail": "barrier", "free": "road", "gotojail": "hand",
         "chance": "shuffle", "chest": "gem", "tax": "coin", "rr": "cart", "util": "bolt"}
JAIL_SQUARE = 10
BAIL = 50
START_CASH = 1500
GO_SALARY = 200
RESERVE = 300                 # the "Cash cushion" threshold

#: The compact card deck: (kind, amount, text).
CARDS = (
    ("gain", 200, "Bank error in your favor: collect $200"),
    ("gain", 100, "You inherit $100"),
    ("gain", 50, "Collect $50 from the bank"),
    ("pay", 50, "Doctor's fee: pay $50"),
    ("pay", 100, "Pay $100 in taxes"),
    ("go", 0, "Advance to GO: collect $200"),
    ("jail", 0, "Go directly to jail"),
    ("repairs", 25, "Street repairs: pay $25 per house"),
)


def hcost(square: int) -> int:
    return HOUSE_COST[SQUARES[square][2]]


@dataclass(kw_only=True)
class MonopolyState(DiceState):
    pos: list[int] = field(default_factory=lambda: [0, 0])
    cash: list[int] = field(default_factory=lambda: [START_CASH, START_CASH])
    owner: list[int] = field(default_factory=lambda: [-1] * 40)
    houses: list[int] = field(default_factory=lambda: [0] * 40)
    jail: list[bool] = field(default_factory=lambda: [False, False])
    #: Failed doubles tries in jail.
    tries: list[int] = field(default_factory=lambda: [0, 0])
    #: What happens next: ``roll``, ``jailroll``, ``card`` (chance nodes),
    #: ``jail``, ``buy``, ``build`` (decisions), or the forced ``start``,
    #: ``after``, ``endroll``, ``next``.
    stage: str = "start"
    #: Pair rolled last, and its sum (utility rent uses it).
    dice: tuple[int, int] = (0, 0)
    total: int = 7
    #: The last roll was a double (another roll follows), and doubles so far.
    extra: bool = False
    doubles: int = 0
    #: Square offered for purchase.
    buy_sq: int = -1
    #: Turns finished so far.
    rounds: int = 0
    #: Seat that went bankrupt, or -1.
    dead: int = -1
    over: bool = False
    #: ``(seat, square)`` of the latest move, for the scene.
    last: tuple[int, int] | None = None


class Monopoly(RollAndMoveGame):
    id = "monopoly"
    name = "Monopoly"
    icon = "money"
    tagline = "Buy, build, bankrupt. Answer the questions that matter."
    chapter = "dice-and-choice"
    order = 30
    concepts = ("probability", "expected-value", "risk", "policy", "luck-vs-skill", "simulation")
    num_players = 2
    max_steps = 6000

    params = {
        "rounds": Param(60, "Turns each", "After this many turns each, the richer player wins.",
                        min=20, max=200),
    }

    rulebook = Rulebook(
        summary="Buy streets, collect rent, build houses and bankrupt your opponent. In this "
                "duel the dice run by themselves and you answer three questions: buy it? "
                "build on it? pay your way out of jail?",
        steps=(
            ("Move", "Each turn the dice move your token around the 40 squares. Passing or "
                     "reaching GO pays $200. A double gives another roll. A third double in a "
                     "row sends you to jail."),
            ("Landing", "An unowned street, railroad or utility can be bought at its price. "
                        "Land on an owned one and you pay rent. Taxes go to the bank. Chance "
                        "and Community Chest draw a card. Go To Jail sends you to jail."),
            ("Rent", "A street pays its base rent, double if the owner holds the whole color "
                     "group without houses. Houses raise it a lot. Railroads pay 25, 50, 100 "
                     "or 200 for 1 to 4 owned, utilities 4 or 10 times your roll."),
            ("Building", "Own a whole color group and you may build houses on its streets, "
                         "evenly, up to 4 per street."),
            ("Jail", "In jail you may pay the 50 dollar bail before you roll, or roll for "
                     "doubles. After three failures you pay the bail and move by your roll."),
            ("Winning", "A player who cannot pay a debt after selling all houses and streets "
                        "is bankrupt and loses. After the turn limit the richer player wins."),
        ),
        extra=(
            ("No auctions", "If you decline to buy, the square stays unowned. The official "
                            "game auctions it."),
            ("No trading, no mortgages", "There are no trades and no mortgages. A player who "
                                         "owes more than they hold must sell houses, then "
                                         "streets, to the bank at half price."),
            ("No hotels", "At most 4 houses per street. Rent is the base rent times 1, 5, 15, "
                          "30 or 40, a simplification of the printed rent tables."),
            ("Compact cards", "Chance and Community Chest are one deck of 8 cards drawn with "
                              "replacement: money in, money out, advance to GO, go to jail, "
                              "repairs. There is no Get Out of Jail Free card."),
            ("Tax and time", "Income tax is a flat $200, as in the official short game. The "
                             "game stops after a turn limit and the richer player wins, "
                             "like the official time limit game."),
        ),
        source="https://www.hasbro.com/common/instruct/monins.pdf",
    )

    models = (
        Model("board", "Everything on the table", True,
              state="both players' squares, cash, jail status, who owns each street and "
                    "how many houses, plus the turn stage and the dice",
              size="astronomical: 40 squares x cash x ownership of 28 properties x houses",
              actions="buy or skip, build on one street or stop, pay bail or wait",
              transition="the dice and the card deck are fresh every turn, so the table "
                         "decides everything that can still happen.",
              reward="+1 win / -1 loss at the end (richer after the turn limit); gamma = 1",
              note="The honest state. Nothing is hidden. It is too big to tabulate, which "
                   "is why Monopoly needs features, not a table."),
        Model("assets", "Cash, square and set progress", "approx",
              state="your cash in buckets, your square, how many streets of each color "
                    "group each player owns, houses built, jail status",
              size="about 10^9 positions",
              actions="the same decisions",
              transition="exact squares of the opponent are dropped.",
              reward="+1 / -1 at the end",
              note="What decides games is who completes color groups first. Counting "
                   "streets per group keeps that and drops which street exactly. Rent on "
                   "a specific square then depends on a detail the state no longer has."),
        Model("cash-square", "Cash and square only", False,
              state="my cash and my square",
              size="a few hundred thousand positions",
              actions="buy or skip, build, pay bail or wait",
              transition="unknown: rent depends on who owns what",
              reward="+1 / -1 at the end",
              note="The two numbers on every player's mind, and not enough. Whether "
                   "buying Boardwalk is good depends on what you and your opponent already "
                   "own, which is history the state forgot."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Flips a coin for every purchase. Lands on Boardwalk, "
            "shrugs.", 1, icon="dice"),
        Bot("tina", "Tina Tightwad", "Never spends a dollar she does not absolutely have to.",
            2, cards=("cushion", "bargain", "spread", "sit-jail"), icon="coin"),
        Bot("bobby", "Bobby Buy-It-All", "If it is for sale, it is his. Houses on everything.",
            3, cards=("buy-all", "builder", "pay-jail"), icon="cart"),
        Bot("mona", "Mogul Mona", "Sets, denial, railroads, houses, in exactly that order.", 4,
            cards=("set-hunter", "blocker", "tycoon", "builder", "cushion", "bargain",
                   "sit-jail"), icon="crown"),
    )

    challenges = (
        Challenge("finish", "Play a game to the end", "finish"),
        Challenge("beat-tina", "Beat Tina Tightwad", "win", 1, bot="tina"),
        Challenge("odds", "Open the odds lens and look at one roll", "lens", 1, lens="odds"),
        Challenge("beat-mona", "Beat Mogul Mona", "win", 2, bot="mona"),
        Challenge("stack-vs-randy", "Build a card stack that beats Randy Rookie in 60 of 100 "
                  "games", "sim", 3, bot="randy", value=0.6),
    )

    # ------------------------------------------------------------------ helpers
    def group_complete(self, s: MonopolyState, group: int, seat: int) -> bool:
        return all(s.owner[i] == seat for i in GROUPS[group])

    def rent(self, s: MonopolyState, square: int) -> int:
        _, kind, group, _, base = SQUARES[square]
        owner = s.owner[square]
        if kind == "rr":
            return 25 * 2 ** (sum(1 for i in RAILROADS if s.owner[i] == owner) - 1)
        if kind == "util":
            both = all(s.owner[i] == owner for i in UTILITIES)
            return (10 if both else 4) * s.total
        if s.houses[square]:
            return base * RENT_MULTIPLIER[s.houses[square]]
        return base * 2 if self.group_complete(s, group, owner) else base

    def build_options(self, s: MonopolyState, seat: int) -> list[int]:
        """Streets where ``seat`` may build now: whole group, evenly, and affordable."""
        out = []
        for g, squares in enumerate(GROUPS):
            if not self.group_complete(s, g, seat):
                continue
            low = min(s.houses[i] for i in squares)
            if low >= MAX_HOUSES or s.cash[seat] < HOUSE_COST[g]:
                continue
            out += [i for i in squares if s.houses[i] == low]
        return out

    def net_worth(self, s: MonopolyState, seat: int) -> int:
        worth = s.cash[seat]
        for i, o in enumerate(s.owner):
            if o == seat:
                worth += SQUARES[i][3] + s.houses[i] * hcost(i) if SQUARES[i][1] == "prop" \
                    else SQUARES[i][3]
        return worth

    def property_count(self, s: MonopolyState, seat: int) -> int:
        return sum(1 for o in s.owner if o == seat)

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> MonopolyState:
        return self.settle(MonopolyState())

    def is_terminal(self, s: MonopolyState) -> bool:
        return s.over

    def winner(self, s: MonopolyState) -> int | None:
        if s.dead >= 0:
            return 1 - s.dead
        a, b = self.net_worth(s, 0), self.net_worth(s, 1)
        return None if a == b else (0 if a > b else 1)

    def timeout_returns(self, s: MonopolyState) -> list[float]:
        return self.returns_from_scores([self.net_worth(s, 0), self.net_worth(s, 1)])

    def chance_outcomes(self, s: MonopolyState) -> list[tuple[Action, float]]:
        if s.stage == "card":
            return [(i, 1 / len(CARDS)) for i in range(len(CARDS))]
        return self.pair_outcomes()

    def legal_actions(self, s: MonopolyState) -> list[Action]:
        if s.stage == "jail":
            return ["pay", "wait"]
        if s.stage == "buy":
            return ["buy", "skip"]
        return [f"build:{i}" for i in self.build_options(s, s.turn)] + ["done"]

    def settle(self, s: MonopolyState) -> MonopolyState:
        """Run forced steps until a chance node or a decision is due."""
        while not s.over:
            p = s.turn
            if s.stage == "start":
                if s.jail[p]:
                    if s.cash[p] >= BAIL:
                        s.stage, s.to_move = "jail", p
                        return s
                    s.stage, s.to_move = "jailroll", CHANCE
                    return s
                s.stage, s.to_move = "roll", CHANCE
                return s
            if s.stage == "after":
                if self.build_options(s, p):
                    s.stage, s.to_move = "build", p
                    return s
                s.stage = "endroll"
            elif s.stage == "endroll":
                if s.extra and not s.jail[p] and s.dead < 0:
                    s.stage, s.to_move = "roll", CHANCE
                    return s
                s.stage = "next"
            elif s.stage == "next":
                s.rounds += 1
                if s.dead >= 0 or s.rounds >= 2 * self.p["rounds"]:
                    s.over = True
                    return s
                s.turn = 1 - p
                s.doubles = 0
                s.extra = False
                s.stage = "start"
            else:
                return s
        return s

    def move(self, s: MonopolyState, a: Action) -> None:
        super().move(s, a)
        if s.dead >= 0:
            s.over = True
        else:
            self.settle(s)

    def charge(self, s: MonopolyState, seat: int, amount: int, to: int = -1) -> None:
        """Pay ``amount``; a shortfall is raised by selling at half price, else bankruptcy."""
        s.cash[seat] -= amount
        if to >= 0:
            s.cash[to] += amount
        while s.cash[seat] < 0:
            best = -1
            for g, squares in enumerate(GROUPS):          # sell evenly: from the tallest street
                mine = [i for i in squares if s.owner[i] == seat and s.houses[i] > 0]
                if mine:
                    top = max(s.houses[i] for i in mine)
                    cand = [i for i in mine if s.houses[i] == top][-1]
                    if best < 0 or HOUSE_COST[g] >= hcost(best):
                        best = cand
            if best >= 0:
                s.houses[best] -= 1
                s.cash[seat] += hcost(best) // 2
                continue
            owned = [i for i, o in enumerate(s.owner) if o == seat]
            if owned:
                cheapest = min(owned, key=lambda i: (SQUARES[i][3], i))
                s.owner[cheapest] = -1
                s.cash[seat] += SQUARES[cheapest][3] // 2
                continue
            s.dead = seat
            return

    def _go_to_jail(self, s: MonopolyState, seat: int) -> None:
        s.pos[seat] = JAIL_SQUARE
        s.jail[seat] = True
        s.tries[seat] = 0
        s.extra = False
        s.stage = "next"
        s.last = (seat, JAIL_SQUARE)

    def _land(self, s: MonopolyState, seat: int) -> None:
        sq = s.pos[seat]
        name, kind, group, price, _ = SQUARES[sq]
        s.last = (seat, sq)
        s.stage = "after"
        if kind in ("prop", "rr", "util"):
            owner = s.owner[sq]
            if owner < 0:
                if s.cash[seat] >= price:
                    s.stage, s.buy_sq = "buy", sq
                    s.to_move = seat
            elif owner != seat:
                self.charge(s, seat, self.rent(s, sq), owner)
        elif kind == "tax":
            self.charge(s, seat, price)
        elif kind == "gotojail":
            self._go_to_jail(s, seat)
        elif kind in ("chance", "chest"):
            s.stage, s.to_move = "card", CHANCE

    def resolve_chance(self, s: MonopolyState, a: Action) -> None:
        p = s.turn
        if s.stage == "card":
            kind, amount, _ = CARDS[int(a)]
            s.stage = "after"
            if kind == "gain":
                s.cash[p] += amount
            elif kind == "pay":
                self.charge(s, p, amount)
            elif kind == "go":
                s.pos[p] = 0
                s.cash[p] += GO_SALARY
            elif kind == "jail":
                self._go_to_jail(s, p)
            else:
                houses = sum(s.houses[i] for i, o in enumerate(s.owner) if o == p)
                if houses:
                    self.charge(s, p, houses * amount)
            return
        d1, d2 = self.parse_pair(a)
        s.dice, s.total = (d1, d2), d1 + d2
        if s.stage == "jailroll":
            s.extra = False
            if d1 == d2:
                s.jail[p] = False
            else:
                s.tries[p] += 1
                if s.tries[p] < 3:
                    s.stage = "next"
                    return
                self.charge(s, p, BAIL)
                if s.dead >= 0:
                    return
                s.jail[p] = False
            s.pos[p] = JAIL_SQUARE + s.total
            self._land(s, p)
            return
        s.extra = d1 == d2
        if s.extra:
            s.doubles += 1
            if s.doubles >= 3:
                self._go_to_jail(s, p)
                return
        step = self.advance(s.pos[p], s.total, 39, "loop")
        if 0 in step.path:
            s.cash[p] += GO_SALARY
        s.pos[p] = step.dest
        self._land(s, p)

    def play(self, s: MonopolyState, a: Action) -> None:
        p = s.turn
        if a == "pay":
            s.cash[p] -= BAIL
            s.jail[p] = False
            s.stage = "roll"
            s.to_move = CHANCE
        elif a == "wait":
            s.stage, s.to_move = "jailroll", CHANCE
        elif a == "buy":
            s.cash[p] -= SQUARES[s.buy_sq][3]
            s.owner[s.buy_sq] = p
            s.stage = "after"
        elif a == "skip":
            s.stage = "after"
        elif a == "done":
            s.stage = "endroll"
        else:
            sq = int(str(a).split(":")[1])
            s.cash[p] -= hcost(sq)
            s.houses[sq] += 1
            s.stage = "after"                             # more building, or on

    # ------------------------------------------------------------ analysis hooks
    def key(self, s: MonopolyState):
        return (tuple(s.pos), tuple(s.cash), tuple(s.owner), tuple(s.houses), tuple(s.jail),
                tuple(s.tries), s.stage, s.turn, s.to_move, s.extra, s.doubles, s.total,
                s.buy_sq, s.rounds, s.dead, s.over)

    def standing(self, s: MonopolyState, seat: int) -> float:
        return float(self.net_worth(s, seat))

    def heuristic(self, s: MonopolyState, player: int) -> float:
        return self.squash(self.net_worth(s, player) - self.net_worth(s, 1 - player), 1500)

    # --------------------------------------------------------------- rule cards
    def _wants(self, s: MonopolyState, candidates, test) -> Action | None:
        if s.stage == "buy" and "buy" in candidates and test(s, SQUARES[s.buy_sq]):
            return "buy"
        return None

    @pick("buy-all", "Buy it all", "If it is for sale and you can pay, buy it. No exceptions.",
          "cart")
    def card_buy_all(self, s, candidates, player, rng):
        return self._wants(s, candidates, lambda s, sq: True)

    @pick("set-hunter", "Set hunter", "Buy streets in color groups you already started.",
          "target")
    def card_set_hunter(self, s, candidates, player, rng):
        return self._wants(s, candidates, lambda s, sq: sq[1] == "prop" and any(
            i != s.buy_sq and s.owner[i] == player for i in GROUPS[sq[2]]))

    @pick("blocker", "Block their set",
          "Buy streets the opponent needs to complete a color group.", "barrier")
    def card_blocker(self, s, candidates, player, rng):
        return self._wants(s, candidates, lambda s, sq: sq[1] == "prop" and any(
            s.owner[i] == 1 - player for i in GROUPS[sq[2]]))

    @pick("tycoon", "Rail tycoon", "Always buy railroads and utilities: steady income.", "cart")
    def card_tycoon(self, s, candidates, player, rng):
        return self._wants(s, candidates, lambda s, sq: sq[1] in ("rr", "util"))

    @pick("bargain", "Bargain bin", "Buy anything priced $200 or less.", "percent")
    def card_bargain(self, s, candidates, player, rng):
        return self._wants(s, candidates, lambda s, sq: sq[3] <= 200)

    @avoid("cushion", "Cash cushion",
           f"Veto purchases and houses that drop you below ${RESERVE}.", "shield")
    def card_cushion(self, s, action, player):
        if action == "buy":
            return s.cash[player] - SQUARES[s.buy_sq][3] < RESERVE
        if str(action).startswith("build:"):
            return s.cash[player] - hcost(int(action.split(":")[1])) < RESERVE
        return False

    @pick("builder", "Master builder",
          "Build houses on your priciest streets first. Rent explodes.", "house")
    def card_builder(self, s, candidates, player, rng):
        builds = [a for a in candidates if str(a).startswith("build:")]
        if not builds:
            return None
        return max(builds, key=lambda a: SQUARES[int(a.split(":")[1])][4])

    @pick("spread", "Even spread", "Build the cheapest, least developed house first.", "wheat")
    def card_spread(self, s, candidates, player, rng):
        builds = [a for a in candidates if str(a).startswith("build:")]
        if not builds:
            return None
        return min(builds, key=lambda a: s.houses[int(a.split(":")[1])] * 1000
                   + hcost(int(a.split(":")[1])))

    @pick("pay-jail", "Bail out", "Pay the $50 immediately: time is money.", "coin")
    def card_pay_jail(self, s, candidates, player, rng):
        return "pay" if "pay" in candidates else None

    @pick("sit-jail", "Cozy cell",
          "Stay put and roll for doubles. Jail is rent-free real estate.", "home")
    def card_sit_jail(self, s, candidates, player, rng):
        return "wait" if "wait" in candidates else None

    # ------------------------------------------------------------ presentation
    def move_label(self, s: MonopolyState, a: Action) -> str:
        if a == "pay":
            return f"Pay ${BAIL} bail"
        if a == "wait":
            return "Roll for doubles"
        if a == "buy":
            name, _, _, price, _ = SQUARES[s.buy_sq]
            return f"Buy {name} for ${price}"
        if a == "skip":
            return "Pass"
        if a == "done":
            return "Stop building"
        sq = int(str(a).split(":")[1])
        return f"Build on {SQUARES[sq][0]} (${hcost(sq)})"

    def outcome_label(self, s: MonopolyState, a: Action) -> str:
        if s.stage == "card":
            return CARDS[int(a)][2]
        return super().outcome_label(s, a)

    def describe(self, s: MonopolyState, a: Action, player: int) -> str:
        if a == "pay":
            return f"pays the ${BAIL} bail and rolls"
        if a == "wait":
            return "sits tight in jail, hoping for doubles"
        if a == "buy":
            return f"buys {SQUARES[s.buy_sq][0]} for ${SQUARES[s.buy_sq][3]}"
        if a == "skip":
            return f"passes on {SQUARES[s.buy_sq][0]}"
        if a == "done":
            return "stops building"
        sq = int(str(a).split(":")[1])
        return f"builds a house on {SQUARES[sq][0]} (now {s.houses[sq] + 1})"

    def describe_chance(self, s: MonopolyState, a: Action) -> str:
        p = s.turn
        after = self.apply_action(s, a)
        if s.stage == "card":
            text = CARDS[int(a)][2]
            return "draws: " + text[0].lower() + text[1:]
        text = f"rolls {self.roll_text(a)}"
        if after.jail[p] and not s.jail[p]:
            return text + (" (a third double) and goes to jail" if after.doubles >= 3
                           else " and is sent to jail")
        if s.stage == "jailroll":
            if not after.jail[p]:
                text += " and leaves jail"
                if s.tries[p] >= 2 and not self.is_double(a):
                    text += f" after paying ${BAIL}"
            else:
                return text + ": no doubles, stays in jail"
        name = SQUARES[after.pos[p]][0]
        text += f" and lands on {name}"
        if s.stage == "roll" and s.pos[p] + self.parse_pair(a)[0] + self.parse_pair(a)[1] >= 40:
            text += ", collects $200 for GO"
        opp = 1 - p
        gain = after.cash[opp] - s.cash[opp]
        if gain > 0:
            text += f", pays ${gain} rent"
        elif SQUARES[after.pos[p]][1] == "tax":
            text += f", pays ${SQUARES[after.pos[p]][3]} tax"
        if after.dead == p:
            text += " and goes bankrupt"
        return text

    def status(self, s: MonopolyState, viewer: int | None) -> str:
        if self.is_terminal(s):
            w = self.winner(s)
            if w is None:
                return "Even: a draw"
            how = "the opponent is bankrupt" if s.dead >= 0 else "richer after the last turn"
            return ("You win" if w == viewer else
                    f"{self.seat_label(w)} wins" if viewer is None else "You lose") + f": {how}"
        if s.to_move == CHANCE:
            return {"card": "Drawing a card", "jailroll": "Rolling for doubles"}.get(
                s.stage, "The dice are rolling")
        mine = s.turn == viewer
        who = "You" if mine else self.seat_name(s.turn, viewer)
        if s.stage == "buy":
            name, _, _, price, _ = SQUARES[s.buy_sq]
            return f"{who} landed on {name} (${price}). Buy it?" if mine else \
                f"{who} is deciding whether to buy {name}"
        if s.stage == "jail":
            return f"{who} in jail: pay ${BAIL} or roll for doubles?" if mine else \
                f"{who} is in jail and deciding"
        return "Build houses or stop?" if mine else f"{who} is building"

    def insight(self, stats: dict) -> str | None:
        n = max(1, stats["n"])
        mine, theirs = stats["wins"][0], stats["wins"][1]
        buys = {"buy-all", "set-hunter", "blocker", "tycoon", "bargain"}
        cards = stats.get("cards")
        if cards is not None and not buys & set(cards) and mine < theirs:
            return ("Without a single buy card you only acquire property when the random "
                    "fallback feels like it. In Monopoly, whoever owns the board owns the "
                    "game. Add a buying rule and watch the curve flip.")
        if mine - theirs > 0.25 * n:
            return ("A landslide: your buying and building priorities are clearly sharper. One "
                    "subtlety this simulation rewards: forced sales happen at half price, so a "
                    "cash cushion is not cowardice, it is loss insurance.")
        if abs(mine - theirs) <= 0.1 * n:
            return ("Nearly even, and that is the honest truth about two player Monopoly "
                    "without trading: any sensible buying policy lands within a few percent of "
                    "any other. The dice own this board. The famous knife fights only start "
                    "when humans negotiate.")
        return None

    # ------------------------------------------------------------------ scene
    def _spaces(self, s: MonopolyState, build: set[int]) -> list[dict]:
        spaces = []
        for i, (name, kind, group, price, _) in enumerate(SQUARES):
            tone = GROUP_TONES[group] if kind == "prop" else ""
            sub = f"${price}" if price and kind != "tax" else (f"pay ${price}" if price else "")
            owner = s.owner[i] if s.owner[i] >= 0 else None
            spaces.append(scene.space(
                name, sub=sub, tone=tone, icon=ICONS.get(kind, ""), owner=owner,
                level=s.houses[i],
                action=f"build:{i}" if i in build else None))
        return spaces

    def scene(self, s: MonopolyState, viewer: int | None) -> dict:
        deciding = not s.over and s.to_move >= 0 and viewer in (None, s.to_move)
        build = {int(a.split(":")[1]) for a in self.legal_actions(s)
                 if str(a).startswith("build:")} if deciding and s.stage == "build" else set()
        parts = [scene.track(self._spaces(s, build), self.token_marks(s.pos), shape="ring",
                             caption=f"Turn {min(s.rounds // 2 + 1, self.p['rounds'])} "
                                     f"of {self.p['rounds']}")]
        if s.dice[0]:
            roller = self.seat_name(s.turn, viewer)
            parts.append(self.dice_part(s.dice, fresh=s.fresh,
                                        caption=f"{roller} rolled" if s.fresh else "Last roll"))
        for seat in range(2):
            items = [("Cash", f"${s.cash[seat]}"),
                     ("Properties", self.property_count(s, seat)),
                     ("Houses", sum(s.houses[i] for i, o in enumerate(s.owner) if o == seat)),
                     ("Net worth", f"${self.net_worth(s, seat)}")]
            if s.jail[seat]:
                items.append(("Status", "in jail"))
            parts.append(scene.kv(items, caption=self.seat_name(seat, viewer), owner=seat))
        if deciding and s.stage in ("buy", "jail"):
            choices, subs = [], []
            for a in self.legal_actions(s):
                choices.append((a, self.move_label(s, a)))
                subs.append(self._hint(s, a))
            parts.append(scene.buttons(choices, sub=subs))
        elif deciding and s.stage == "build":
            parts.append(scene.buttons([("done", "Stop building")],
                                       caption="Click a street on the board to build there"))
        players = self.scoreboard(s, viewer, score=lambda i: f"${s.cash[i]}",
                                  sub=lambda i: f"{self.property_count(s, i)} properties, "
                                                f"net worth ${self.net_worth(s, i)}")
        return scene.scene(parts, players=players, status=self.status(s, viewer))

    def _hint(self, s: MonopolyState, a: Action) -> str:
        if a == "buy":
            name, kind, group, price, base = SQUARES[s.buy_sq]
            left = s.cash[s.turn] - price
            mates = ""
            if kind == "prop":
                have = sum(1 for i in GROUPS[group] if s.owner[i] == s.turn)
                mates = f" You hold {have} of {len(GROUPS[group])} in this color."
            return f"Leaves you ${left}.{mates}"
        if a == "skip":
            return "Nobody gets it. No auction in this game."
        if a == "pay":
            return f"Leaves you ${s.cash[s.turn] - BAIL}. You move at once."
        if a == "wait":
            return f"Doubles frees you. Failed tries so far: {s.tries[s.turn]} of 3."
        return ""
