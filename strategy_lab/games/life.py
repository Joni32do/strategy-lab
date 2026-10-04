"""The Game of Life: a simplified race to retirement.

A single life road from the start (square 0) to retirement (square 60). A
spinner (1..10) moves you along. Passing a payday square collects your salary.
Net worth (cash, with the retirement payout folded in) decides the winner. The
two players never interact: each races their own bank balance, so every choice
is a risk and reward lever that a rule card can pull.

This is the lab's own simplified version, not the published rules (there are
no cars, pegs, houses or action tiles). Money is in thousands of dollars.

Decision spaces
---------------
================  ===================================================
``fork``          college (tuition now, higher-tier careers later) or work
``career``        pick a career: steady or high pay, low or high tier
``insure``        buy full insurance (cost now, waives later accidents)
``gamble``        stock market: risk cash on a spin, or walk past
``retire``        Countryside Acres (safe) or Millionaire Estates (spin)
================  ===================================================

Chance nodes: the spinner, a salary swing on risky careers, the 40 percent
accident check on a hazard square, the stock market and the Millionaire
Estates payout. A seat stays on the move through its whole turn (decisions at
the milestone it reaches, then the next player spins).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Rulebook, avoid, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.dice import DiceState, RollAndMoveGame

FINISH = 60
PAYDAY = 8                       # salary at 8, 16, ..., 56
INS_AT = 12
GAMBLE_AT = (24, 40)
HAZARD_AT = (20, 44)
MARRY_AT, BABY_AT = 30, 50

TUITION = 40
INSURANCE_COST = 15
HAZARD_COST = 40
HAZARD_CHANCE = 0.4
GAMBLE_WIN, GAMBLE_LOSE = 40, 30
COUNTRY = 100
ESTATE_PER = 24
MARRY_GIFT, BABY_GIFT = 20, 12


@dataclass(frozen=True)
class Career:
    id: str
    name: str
    pay: int          # per payday, in $k
    swing: int        # salary varies by +/- swing
    college: bool


CAREERS = {c.id: c for c in (
    Career("server", "Server", 12, 0, False),
    Career("sales", "Salesperson", 16, 6, False),
    Career("athlete", "Athlete", 22, 14, False),
    Career("teacher", "Teacher", 20, 0, True),
    Career("lawyer", "Lawyer", 28, 8, True),
    Career("doctor", "Doctor", 34, 10, True),
)}

#: Milestones in road order: (square, stage it triggers, id).
STOPS = (
    (INS_AT, "insure", "ins"),
    (GAMBLE_AT[0], "gamble", "g0"),
    (GAMBLE_AT[1], "gamble", "g1"),
    (FINISH, "retire", "ret"),
)
DECISIONS = ("fork", "career", "insure", "gamble", "retire")


@dataclass(kw_only=True)
class LifeState(DiceState):
    pos: list[int] = field(default_factory=lambda: [0, 0])
    cash: list[int] = field(default_factory=lambda: [0, 0])
    college: list[bool] = field(default_factory=lambda: [False, False])
    career: list[str] = field(default_factory=lambda: ["", ""])
    insured: list[bool] = field(default_factory=lambda: [False, False])
    #: Per seat: ``fork``, ``career``, ``insure``, ``gamble``, ``retire``, ``spin`` or ``done``.
    stage: list[str] = field(default_factory=lambda: ["fork", "fork"])
    #: Per seat: ids of milestones already resolved.
    resolved: list[list[str]] = field(default_factory=lambda: [[], []])
    #: Pending chance node: ``spin``, ``payday``, ``hazard``, ``gamble`` or ``estates``.
    chance: str = ""
    #: Squares of the current move still to be processed.
    pending: list[int] = field(default_factory=list)
    #: The active seat already spun this turn.
    spun: bool = False
    #: The move just finished: look for a milestone.
    arrived: bool = False
    #: Latest spinner result.
    spin: int = 0
    over: bool = False


class Life(RollAndMoveGame):
    id = "life"
    name = "The Game of Life"
    icon = "road"
    tagline = "College or career, safe or bold. Spin the wheel and grow your net worth."
    chapter = "dice-and-choice"
    order = 40
    concepts = ("expected-value", "risk", "variance", "policy", "luck-vs-skill", "simulation")
    num_players = 2

    rulebook = Rulebook(
        summary="Drive along the road of life from the start to retirement. A spinner moves "
                "you, paydays fill your bank, and a few forks let you trade safety for "
                "upside. The richer player at the end wins.",
        steps=(
            ("The road", "Spin the 1 to 10 spinner and move that many squares. Every 8th "
                         "square is a payday: you collect your salary if you have a career. "
                         "Money is in thousands of dollars (k)."),
            ("The fork", "At the start choose college (a 40k loan, higher paying careers) "
                         "or start work at once, then pick a career."),
            ("Insurance", "At square 12 you may buy full insurance for 15k. Hazard squares at "
                          "20 and 44 cost 40k on a 40 percent accident check unless insured."),
            ("The stock market", "At squares 24 and 40 you may bet: win 40k or lose 30k on "
                                 "an even spin, or walk past."),
            ("Retirement", "At square 60 take Countryside Acres for a sure 100k or spin for "
                           "Millionaire Estates: the spin (1 to 10) times 24k."),
            ("Winning", "When both players retire, the player with more cash wins. "
                        "Marriage at 30 (+20k) and a baby at 50 (+12k) add small gifts."),
        ),
        extra=(
            ("Not the published rules", "This is the lab's own simplified version of The "
                                        "Game of Life. It has no cars, pegs or action tiles, "
                                        "and money is in thousands."),
            ("No interaction", "The players never affect each other, so each choice is a pure "
                               "risk and reward decision about your own bank balance."),
        ),
    )

    models = (
        Model("table", "Both lives", True,
              state="both players' squares, cash, career, college, insurance, which "
                    "milestones are done, the stage and the pending dice",
              size="about 10^9 positions",
              actions="fork, career, insurance, market and retirement choices, plus the spin",
              transition="the spinner and the risky events are fresh chance nodes.",
              reward="+1 win / -1 loss at the end; gamma = 1",
              note="Complete. The opponent enters only through the final comparison, "
                   "because nothing a player does changes the other's life."),
        Model("own", "My life only", "approx",
              state="my square, cash, career, college, insurance and resolved milestones",
              size="about 10^6 positions",
              actions="the same choices",
              transition="the same, without the opponent.",
              reward="my final cash in $k",
              note="Markov for maximizing your own net worth, and exact for that goal. It "
                   "cannot say when a gamble is worth it for winning: behind, take "
                   "variance, ahead, play safe. That depends on the other life."),
        Model("cash-square", "Cash and square", False,
              state="my cash and my square",
              size="about 10^4 positions",
              actions="the same choices",
              transition="unknown: income depends on the career",
              reward="my final cash",
              note="The two numbers on the scoreboard. The career decides how much every "
                   "future payday pays, and it is gone from this state, so equal states "
                   "can have very different futures."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Spins the wheel and shrugs at every fork in the road.",
            1, icon="dice"),
        Bot("stan", "Steady Stan", "Takes the steadiest job and never gambles a cent. Safe is "
            "not free: he trails even Randy.", 1, cards=("steady", "safe"), icon="shield"),
        Bot("clara", "Climber Clara", "College, the best salary she can get, and full "
            "insurance.", 3, cards=("college", "big-salary", "insured"), icon="trophy"),
        Bot("vera", "Venture Vera", "A doctorate, top pay, insured against hazards, and bold "
            "at the market.", 4, cards=("college", "big-salary", "insured", "high-roller"),
            icon="star"),
    )

    challenges = (
        Challenge("finish", "Retire", "finish"),
        Challenge("beat-stan", "Beat Steady Stan", "win", 1, bot="stan"),
        Challenge("model", "Open the model lens and compare the state spaces", "lens", 1,
                  lens="model"),
        Challenge("beat-vera", "Beat Venture Vera", "win", 2, bot="vera"),
        Challenge("stack-vs-clara", "Build a card stack that beats Climber Clara in 55 of 100 "
                  "games", "sim", 3, bot="clara", value=0.55),
    )

    # ------------------------------------------------------------------ rules
    def initial_state(self) -> LifeState:
        return self.settle(LifeState())

    def is_terminal(self, s: LifeState) -> bool:
        return s.over

    def winner(self, s: LifeState) -> int | None:
        a, b = s.cash
        return None if a == b else (0 if a > b else 1)

    def timeout_returns(self, s: LifeState) -> list[float]:
        return self.returns_from_scores(s.cash)

    def chance_outcomes(self, s: LifeState) -> list[tuple[Action, float]]:
        if s.chance == "spin" or s.chance == "estates":
            return self.die_outcomes(10)
        if s.chance == "payday":
            swing = CAREERS[s.career[s.turn]].swing
            n = 2 * swing + 1
            return [(v, 1.0 / n) for v in range(n)]
        if s.chance == "hazard":
            return [(1, HAZARD_CHANCE), (0, 1 - HAZARD_CHANCE)]
        return [(1, 0.5), (0, 0.5)]                       # the stock market: spin 6..10 wins

    def legal_actions(self, s: LifeState) -> list[Action]:
        p = s.turn
        stage = s.stage[p]
        if stage == "fork":
            return ["college", "work"]
        if stage == "career":
            return [f"career:{c.id}" for c in CAREERS.values() if c.college == s.college[p]]
        if stage == "insure":
            return ["buy-insurance", "no-insurance"]
        if stage == "gamble":
            return ["bet", "no-bet"]
        return ["country", "estates"]

    def _next_stage(self, s: LifeState, p: int) -> None:
        """Pick the seat's stage: the first milestone reached and not yet resolved, else spin."""
        for at, stage, stop_id in STOPS:
            if stop_id not in s.resolved[p] and s.pos[p] >= at:
                s.stage[p] = stage
                return
        s.stage[p] = "done" if "ret" in s.resolved[p] else "spin"

    def _next_actor(self, s: LifeState) -> int:
        other = 1 - s.turn
        if s.stage[other] != "done":
            return other
        return s.turn if s.stage[s.turn] != "done" else other

    def settle(self, s: LifeState) -> LifeState:
        """Run forced steps until a chance node or a decision is due."""
        while True:
            if s.chance:
                return s                                   # an outcome is still due
            p = s.turn
            if s.stage[0] == "done" and s.stage[1] == "done":
                s.over = True
                return s
            if s.pending:
                sq = s.pending.pop(0)
                s.pos[p] = sq
                career = CAREERS.get(s.career[p])
                if sq % PAYDAY == 0 and career:
                    if career.swing:
                        s.chance, s.to_move = "payday", CHANCE
                        return s
                    s.cash[p] += career.pay
                if sq in HAZARD_AT and not s.insured[p]:
                    s.chance, s.to_move = "hazard", CHANCE
                    return s
                if sq == MARRY_AT:
                    s.cash[p] += MARRY_GIFT
                if sq == BABY_AT:
                    s.cash[p] += BABY_GIFT
                continue
            if s.arrived:
                s.arrived = False
                self._next_stage(s, p)
            stage = s.stage[p]
            if stage in DECISIONS:
                s.to_move = p
                return s
            if stage == "spin" and not s.spun:
                s.chance, s.to_move = "spin", CHANCE
                return s
            s.turn = self._next_actor(s)                   # this seat's turn is over
            s.spun = False

    def move(self, s: LifeState, a: Action) -> None:
        super().move(s, a)
        self.settle(s)

    def resolve_chance(self, s: LifeState, a: Action) -> None:
        p, kind, v = s.turn, s.chance, int(a)
        s.chance = ""
        if kind == "spin":
            s.spin, s.spun, s.arrived = v, True, True
            s.pending = list(self.advance(s.pos[p], v, FINISH, "stop").path)
        elif kind == "payday":
            career = CAREERS[s.career[p]]
            s.cash[p] += career.pay + v - career.swing
        elif kind == "hazard":
            if v:
                s.cash[p] -= HAZARD_COST
        elif kind == "gamble":
            s.cash[p] += GAMBLE_WIN if v else -GAMBLE_LOSE
            s.arrived = True
        else:                                              # estates
            s.cash[p] += v * ESTATE_PER
            s.stage[p] = "done"

    def play(self, s: LifeState, a: Action) -> None:
        p = s.turn
        a = str(a)
        if a in ("college", "work"):
            if a == "college":
                s.college[p] = True
                s.cash[p] -= TUITION
            s.stage[p] = "career"
        elif a.startswith("career:"):
            s.career[p] = a.split(":")[1]
            self._next_stage(s, p)
        elif a in ("buy-insurance", "no-insurance"):
            if a == "buy-insurance":
                s.insured[p] = True
                s.cash[p] -= INSURANCE_COST
            s.resolved[p].append("ins")
            self._next_stage(s, p)
        elif a in ("bet", "no-bet"):
            at = GAMBLE_AT[0] if "g0" not in s.resolved[p] else GAMBLE_AT[1]
            s.resolved[p].append("g0" if at == GAMBLE_AT[0] else "g1")
            if a == "bet":
                s.chance, s.to_move = "gamble", CHANCE
            else:
                self._next_stage(s, p)
        elif a == "country":
            s.cash[p] += COUNTRY
            s.resolved[p].append("ret")
            s.stage[p] = "done"
        else:                                              # estates: spin for the payout
            s.resolved[p].append("ret")
            s.chance, s.to_move = "estates", CHANCE

    # ------------------------------------------------------------ analysis hooks
    def key(self, s: LifeState):
        return (tuple(s.pos), tuple(s.cash), tuple(s.college), tuple(s.career),
                tuple(s.insured), tuple(s.stage), tuple(tuple(r) for r in s.resolved),
                s.chance, tuple(s.pending), s.turn, s.to_move, s.spun, s.arrived, s.over)

    def standing(self, s: LifeState, seat: int) -> float:
        return float(s.cash[seat])

    def heuristic(self, s: LifeState, player: int) -> float:
        return self.squash(s.cash[player] - s.cash[1 - player], 150)

    # --------------------------------------------------------------- rule cards
    @pick("college", "Go to college",
          "Take the college fork. A student loan now buys higher tier careers later.", "sparkle")
    def card_college(self, s: LifeState, candidates, player, rng):
        return "college" if "college" in candidates else None

    def _careers(self, candidates) -> list[Career]:
        return [CAREERS[a.split(":")[1]] for a in candidates if str(a).startswith("career:")]

    @pick("big-salary", "Chase the big salary",
          "At the career space, always take the highest paying job on offer.", "money")
    def card_big_salary(self, s: LifeState, candidates, player, rng):
        jobs = self._careers(candidates)
        return f"career:{max(jobs, key=lambda c: c.pay).id}" if jobs else None

    @pick("steady", "Steady paycheck",
          "Prefer the most predictable career: lowest swing, no payday surprises.", "scale")
    def card_steady(self, s: LifeState, candidates, player, rng):
        jobs = self._careers(candidates)
        if not jobs:
            return None
        return f"career:{min(jobs, key=lambda c: (c.swing, -c.pay)).id}"

    @pick("insured", "Always insured",
          "Buy full insurance: a fixed cost that waives every later hazard space.", "shield")
    def card_insured(self, s: LifeState, candidates, player, rng):
        return "buy-insurance" if "buy-insurance" in candidates else None

    @pick("high-roller", "High roller",
          "Play the stock market and bet retirement on Millionaire Estates.", "slot")
    def card_high_roller(self, s: LifeState, candidates, player, rng):
        for a in ("bet", "estates"):
            if a in candidates:
                return a
        return None

    @avoid("safe", "Play it safe",
           "Never gamble on the stock market. Retire to guaranteed Countryside Acres.",
           "barrier")
    def card_safe(self, s: LifeState, action, player):
        return action in ("bet", "estates")

    # ------------------------------------------------------------ presentation
    def move_label(self, s: LifeState, a: Action) -> str:
        a = str(a)
        if a.startswith("career:"):
            c = CAREERS[a.split(":")[1]]
            return f"{c.name} (${c.pay}k per payday)"
        return {
            "college": f"Go to college (-${TUITION}k)", "work": "Start working",
            "buy-insurance": f"Buy insurance (-${INSURANCE_COST}k)", "no-insurance": "Skip it",
            "bet": "Bet on the market", "no-bet": "Walk past",
            "country": f"Countryside Acres (+${COUNTRY}k)",
            "estates": "Millionaire Estates (spin)",
        }[a]

    def describe(self, s: LifeState, a: Action, player: int) -> str:
        a = str(a)
        if a.startswith("career:"):
            c = CAREERS[a.split(":")[1]]
            return f"takes the {c.name} career (${c.pay}k per payday)"
        return {
            "college": f"heads to college on a ${TUITION}k student loan",
            "work": "skips college and starts working right away",
            "buy-insurance": f"buys full insurance for ${INSURANCE_COST}k",
            "no-insurance": "declines insurance and hopes for the best",
            "bet": "risks cash on the stock market",
            "no-bet": "walks past the stock market",
            "country": f"retires to Countryside Acres (+${COUNTRY}k)",
            "estates": "bets retirement on Millionaire Estates",
        }[a]

    def outcome_label(self, s: LifeState, a: Action) -> str:
        if s.chance == "hazard":
            return "accident" if a == 1 else "safe"
        if s.chance == "gamble":
            return "win" if a == 1 else "loss"
        if s.chance == "payday":
            c = CAREERS[s.career[s.turn]]
            return f"${c.pay + int(a) - c.swing}k"
        return str(a)

    def describe_chance(self, s: LifeState, a: Action) -> str:
        p, v = s.turn, int(a)
        if s.chance == "spin":
            return f"spins a {v}"
        if s.chance == "payday":
            c = CAREERS[s.career[p]]
            return f"collects a payday of ${c.pay + v - c.swing}k"
        if s.chance == "hazard":
            return f"has an accident: -${HAZARD_COST}k" if v else "passes a hazard square unharmed"
        if s.chance == "gamble":
            return (f"wins big at the market: +${GAMBLE_WIN}k" if v
                    else f"loses at the market: -${GAMBLE_LOSE}k")
        return f"cashes out Millionaire Estates after a spin of {v}: +${v * ESTATE_PER}k"

    def status(self, s: LifeState, viewer: int | None) -> str:
        if self.is_terminal(s):
            w = self.winner(s)
            if w is None:
                return f"Even at ${s.cash[0]}k: a draw"
            if viewer is None:
                return f"{self.seat_label(w)} wins with ${s.cash[w]}k"
            return (f"You win with ${s.cash[w]}k" if w == viewer
                    else f"You lose: ${s.cash[viewer]}k against ${s.cash[w]}k")
        if s.to_move == CHANCE:
            return {"spin": "Spinning", "estates": "Spinning for Millionaire Estates",
                    "payday": "Payday", "hazard": "Hazard check",
                    "gamble": "The market decides"}[s.chance]
        p = s.turn
        who = "You" if p == viewer else self.seat_name(p, viewer)
        text = {"fork": "College or work?", "career": "Choose a career",
                "insure": "Buy insurance?", "gamble": "Bet on the stock market?",
                "retire": "Retire safely or spin for the estates?"}[s.stage[p]]
        return text if p == viewer else f"{who}: {text.lower()}"

    def insight(self, stats: dict) -> str | None:
        n = max(1, stats["n"])
        mine, theirs = stats["wins"][0], stats["wins"][1]
        cards = stats.get("cards")
        if (cards is not None and not {"college", "big-salary"} & set(cards)
                and mine < theirs):
            return ("Net worth is mostly salary times paydays. Without a career card you take "
                    "whatever job the random fallback lands on. Add Go to college and Chase "
                    "the big salary and the income gap does the rest. The gambles are noise "
                    "on top.")
        if cards is not None and "safe" in cards and mine < theirs:
            return ("Safety costs money here. The stock market pays +$5k on average per bet and "
                    "Millionaire Estates pays $132k on average against a sure $100k. A stack "
                    "that never gambles gives that expected value away. Risk only hurts when "
                    "you are already ahead.")
        if mine >= 0.62 * n:
            return ("Convincing. The big lever here is expected income (college and top "
                    "salary), not the spinner. Insurance trims your downside. The stock market "
                    "and Millionaire Estates are slightly positive bets, worth taking once "
                    "your salary already leads.")
        if abs(mine - theirs) <= 0.1 * n:
            return ("Nearly even. Two sensible income plans converge, and from there the "
                    "spinner, the hazards and the retirement gamble add variance that no card "
                    "can steer. Recognizing where skill stops and luck takes over is a "
                    "strategy insight in itself.")
        return None

    # ------------------------------------------------------------------ scene
    def _spaces(self) -> list[dict]:
        out = []
        for i in range(FINISH + 1):
            if i == 0:
                sp = scene.space("Start", tone="start", icon="flag")
            elif i == FINISH:
                sp = scene.space("Retire", sub="$100k or spin", tone="goal", icon="home")
            elif i == INS_AT:
                sp = scene.space(str(i), sub="Insurance", tone="safe", icon="shield")
            elif i in GAMBLE_AT:
                sp = scene.space(str(i), sub="Market", tone="hot", icon="slot")
            elif i in HAZARD_AT:
                sp = scene.space(str(i), sub="Hazard", tone="bad", icon="bolt")
            elif i == MARRY_AT:
                sp = scene.space(str(i), sub="Marriage +$20k", tone="good", icon="heart")
            elif i == BABY_AT:
                sp = scene.space(str(i), sub="Baby +$12k", tone="good", icon="smile")
            elif i % PAYDAY == 0:
                sp = scene.space(str(i), sub="Payday", tone="good", icon="money")
            else:
                sp = scene.space(str(i), tone="muted")
            out.append(sp)
        return out

    def _career_text(self, s: LifeState, seat: int) -> str:
        if s.career[seat]:
            return CAREERS[s.career[seat]].name
        return "in college" if s.college[seat] else "none yet"

    def _hint(self, s: LifeState, a: str) -> str:
        if a.startswith("career:"):
            c = CAREERS[a.split(":")[1]]
            swing = (f", varies by plus or minus ${c.swing}k" if c.swing
                     else ", always the same")
            return f"${c.pay}k per payday{swing}."
        return {
            "college": f"Costs ${TUITION}k now. Doctors, lawyers and teachers become possible.",
            "work": "No debt. Server, salesperson or athlete.",
            "buy-insurance": f"Costs ${INSURANCE_COST}k. A hazard costs ${HAZARD_COST}k with "
                             f"chance {HAZARD_CHANCE:.0%}, and two hazards lie ahead.",
            "no-insurance": f"Each hazard costs ${HAZARD_COST}k with chance {HAZARD_CHANCE:.0%}.",
            "bet": f"Even chance: +${GAMBLE_WIN}k or -${GAMBLE_LOSE}k. Average +"
                   f"${(GAMBLE_WIN - GAMBLE_LOSE) // 2}k.",
            "no-bet": "Keep what you have.",
            "country": f"A sure ${COUNTRY}k.",
            "estates": f"Spin 1 to 10 times ${ESTATE_PER}k. Average ${5.5 * ESTATE_PER:.0f}k, "
                       "but a low spin pays less than the sure thing.",
        }[a]

    def scene(self, s: LifeState, viewer: int | None) -> dict:
        deciding = not s.over and s.to_move >= 0 and viewer in (None, s.to_move)
        parts = [scene.track(self._spaces(), self.token_marks(s.pos), shape="serpentine",
                             caption="Payday every 8 squares")]
        if s.spin:
            roller = self.seat_name(s.turn, viewer)
            parts.append(self.dice_part([s.spin], sides=10, fresh=s.fresh and s.chance == "",
                                        caption=f"{roller} spun"))
        for seat in range(2):
            items = [("Cash", f"${s.cash[seat]}k"), ("Career", self._career_text(s, seat)),
                     ("College", "yes" if s.college[seat] else "no"),
                     ("Insured", "yes" if s.insured[seat] else "no")]
            parts.append(scene.kv(items, caption=self.seat_name(seat, viewer), owner=seat))
        if deciding:
            acts = self.legal_actions(s)
            parts.append(scene.buttons([(a, self.move_label(s, a)) for a in acts],
                                       sub=[self._hint(s, str(a)) for a in acts]))
        players = self.scoreboard(
            s, viewer, score=lambda i: f"${s.cash[i]}k",
            sub=lambda i: "retired" if s.stage[i] == "done" else f"square {s.pos[i]}")
        return scene.scene(parts, players=players, status=self.status(s, viewer))
