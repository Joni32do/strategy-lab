"""Doppelkopf: the user's own Python game, played through the OpenSpiel API.

``doppelkopf/`` (repository root) is an OpenSpiel *Python* game registered as
``python_doppelkopf``. This module adapts it like any other engine. Its
docstring states the scope: "Reservations, solos and Re/Kontra announcements
are not modelled." A player dealt both club queens plays a silent wedding.

The state is the Python ``DoppelkopfState`` itself, so the scene reads its
attributes. It builds everything from the viewer's own hand and from public
facts (the cards on the table, points taken, club queens that have been
played). Hidden hands and the full list of Re players are never put into a
viewer's scene.

Bots
----
* Randy: random legal card.
* Cardi: a stack of the family's rule cards ("Win it cheaply", "Dump the lowest").
* Hanni: the repository's ``HeuristicBot`` (``doppelkopf/bots.py``): leads aces,
  feeds a known partner, wins tricks that are worth it.
* Master: the repository's PIMC search (``doppelkopf/search.py``): sample hidden
  hands that fit what the seat has seen, roll each card out, play the best average.
  12 worlds make a whole game of four such seats take about 0.2 seconds.
"""

from __future__ import annotations

import random
from functools import lru_cache

import pyspiel

import doppelkopf.game  # noqa: F401  (registers "python_doppelkopf" with pyspiel)
from doppelkopf import cards as dk
from doppelkopf import search
from doppelkopf.bots import HeuristicBot
from doppelkopf.game import legal_cards

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Param, Policy, Rulebook, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.cards import TableView, TrickTakingGame
from strategy_lab.families.external import SEED_LIMIT

SYMBOL = {"C": "\N{BLACK CLUB SUIT}", "S": "\N{BLACK SPADE SUIT}",
          "H": "\N{BLACK HEART SUIT}", "D": "\N{BLACK DIAMOND SUIT}"}


def card_name(card: int) -> str:
    """Display name such as ``"\N{BLACK CLUB SUIT}Q"``."""
    return SYMBOL[dk.SUIT_LETTERS[dk.suit_of(card)]] + dk.RANK_LETTERS[dk.rank_of(card)]


@lru_cache(maxsize=1)
def _net():
    """The trained policy net for rollouts, or ``None`` (heuristic rollouts)."""
    return search.resolve_net()


class DoppelkopfBotPolicy(Policy):
    """Wraps one of the repository's bots (``HeuristicBot`` or ``MasterBot``).

    Both read the Python state, but only their own hand and public facts.
    The bot is rebuilt per decision from the caller's ``rng``, so a decision
    is deterministic given the seed.
    """

    def __init__(self, kind: str = "heuristic", worlds: int = 12, name: str = "doppelkopf"):
        self.kind = kind
        self.worlds = worlds
        self.name = name

    def _advisor(self, rng: random.Random):
        return search.PIMCAdvisor(num_worlds=self.worlds, net=_net(),
                                  rng=random.Random(rng.randrange(SEED_LIMIT)))

    def act(self, game, s, player, rng):
        if len(game.legal_actions(s)) == 1:
            return game.legal_actions(s)[0]
        if self.kind == "heuristic":
            return int(HeuristicBot(player, random.Random(rng.randrange(SEED_LIMIT))).step(s))
        return int(search.MasterBot(player, self._advisor(rng)).step(s))

    def trace(self, game, s, player):
        """The advisor's expected game points per legal card (fixed seed)."""
        if self.kind != "master":
            return {}
        scores = self._advisor(random.Random(20260710)).evaluate(s, player)
        return {"expected_return": {card_name(c): round(v, 2) for c, v in scores}}


class DoppelkopfView:
    """What one seat sees: its own hand and the public table."""

    def __init__(self, s, seat: int):
        self.seat = seat
        self.hand = dk.sort_for_display(
            [c for c in range(dk.NUM_CARD_TYPES) for _ in range(s.hands[seat][c])])
        self.trick = [((s.trick_leader + i) % dk.NUM_PLAYERS, c)
                      for i, c in enumerate(s.current_trick)]
        self.known_re = set(s.known_re_players())
        self.is_re = seat in s.re_players          # a seat knows its own team


class Doppelkopf(TrickTakingGame):
    id = "doppelkopf"
    name = "Doppelkopf"
    icon = "hands"
    tagline = "Four players, hidden teams, and a partner you have to find first."
    chapter = "hidden"
    order = 30
    concepts = ("imperfect-information", "information-set", "belief", "multi-agent",
                "rule-cards")
    spiel_name = "python_doppelkopf"
    seat_names = ("South", "West", "North", "East")
    others = ("West", "North", "East")
    forward_params = ("second_dulle", "karlchen")
    max_steps = 110

    params = {
        "second_dulle": Param(True, "Second Dulle beats the first",
                              "With two 10 of hearts in a trick, the later one wins."),
        "karlchen": Param(True, "Karlchen",
                          "Winning the last trick with a jack of clubs scores a bonus point."),
    }

    rulebook = Rulebook(
        summary="The German four-player trick-taking classic. The two players holding a "
                "queen of clubs form the hidden Re team against Kontra.",
        steps=(
            ("The deck (48 cards, 240 points)",
             "A doubled 24-card deck: 9, 10, J, Q, K, A in clubs, spades, hearts and "
             "diamonds, every card twice. Points: ace 11, ten 10, king 4, queen 3, jack 2, "
             "nine 0. Each player gets 12 cards."),
            ("Hidden teams: Re and Kontra",
             "Whoever holds a queen of clubs is Re, the other two are Kontra. Nobody says "
             "so: the teams show themselves when the club queens are played. Re wins the "
             "deal with 121 of the 240 points."),
            ("Trumps and their order",
             "One big trump suit, strongest first: 10 of hearts (the Dulle), queens "
             "(clubs, spades, hearts, diamonds), jacks (same order), then ace, ten, king "
             "and nine of diamonds. Every other card is a plain card of its suit, ranked "
             "ace, ten, king, nine."),
            ("Following suit",
             "The first card of a trick sets the led class: trump or a plain suit. You "
             "must play a card of that class if you have one."),
            ("Winning a trick",
             "The highest trump wins, or the highest card of the led suit if no trump was "
             "played. Between two equal cards the first one played wins (the Dulle rule "
             "below is the exception). The winner leads the next trick."),
            ("Scoring",
             "The winning team gets 1 game point, plus one for holding the loser under 90, "
             "under 60 and under 30, one for taking every trick (schwarz), and Kontra gets "
             "one more for winning against the queens. Special points: catching a fox (an "
             "ace of diamonds taken by the other team), a trick of 40 or more points "
             "(Doppelkopf), and the last trick won with a jack of clubs (Karlchen)."),
            ("Silent wedding",
             "A player dealt both club queens plays alone as Re against the other three, "
             "for three times the game value."),
        ),
        extra=(
            ("Not modelled", "The engine's own docstring: \"Reservations, solos and "
                             "Re/Kontra announcements are not modelled.\" (doppelkopf/game.py)"),
            ("Second Dulle (toggle)", "Normally the 10 of hearts is the highest trump. With "
                                      "this rule the later of two Dullen in one trick wins, so "
                                      "a Dulle can be beaten, but only by the other Dulle."),
            ("Karlchen (toggle)", "Winning the very last trick with a jack of clubs scores one "
                                  "extra game point."),
        ),
        source="https://en.wikipedia.org/wiki/Doppelkopf",
    )

    models = (
        Model("hand-trick", "Own hand + current trick", False,
              state="your own hand plus the cards on the table in the current trick",
              actions="legal cards to play (follow the led trump or suit if you can)",
              reward="card points, turned into the game value of Re against Kontra",
              note="Blind to the whole game: you cannot count captured points and, worse, "
                   "you cannot tell who your partner is."),
        Model("hand-trick-counted", "Own hand + trick + cards played + known teams", "approx",
              state="own hand + current trick + every card played so far + points taken "
                    "per seat + which seats have shown a club queen",
              actions="legal cards to play (follow the led class if you can)",
              reward="card points, turned into the game value of Re against Kontra",
              note="Lets you count points and read revealed teams, but drops the exact "
                   "order of play that inference about the two hidden hands needs."),
        Model("info-set", "Full information set (ordered play history)", True,
              state="the whole observed history: every card played, in order and by "
                    "whom, the club queens seen, and your own dealt hand",
              size="the two unseen hands (46 cards minus what you saw) are all that is "
                   "unknown, but the number of consistent deals is huge",
              actions="one legal card per turn, twelve tricks in all",
              transition="the three other players answer; their hands and the team split "
                         "stay hidden",
              reward="Re wins with 121 or more points; the game value adds no 90/60/30, "
                     "schwarz, against the queens and the special points, tripled for a "
                     "lone Re",
              note="The information state OpenSpiel works with, and the only formulation "
                   "in which optimal play under hidden information is well defined."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Plays a random legal card. Wins by accident.", 1,
            icon="dice"),
        Bot("cardi", "Cardi", "Takes tricks cheaply when he can, otherwise throws away his "
            "lowest card. No idea who his partner is.", 2, cards=("cheap-win", "dump"),
            icon="hand"),
        Bot("hanni", "Hanni Heuristic", "Leads aces, feeds her partner once the club "
            "queens show, and only fights for tricks worth taking.", 3,
            policy="hanni_policy", icon="shield"),
        Bot("master", "Master", "Imagines 12 possible deals that fit what he has seen, "
            "plays every card out in each, and picks the best average.", 4,
            policy="master_policy", icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a deal to the end", "finish"),
        Challenge("belief", "Open the belief lens", "lens", 1, lens="belief"),
        Challenge("beat-hanni", "Beat Hanni Heuristic", "win", 2, bot="hanni"),
        Challenge("big-game", "Win a deal worth 3 or more points", "score", 2, value=3.0),
        Challenge("beat-master", "Beat Master", "win", 3, bot="master"),
    )

    # ----------------------------------------------------------------- hooks
    def trick_view(self, s, player) -> DoppelkopfView:
        return DoppelkopfView(s, player)

    def trick_so_far(self, view: DoppelkopfView):
        return view.trick

    def card_points(self, card: int) -> int:
        return dk.card_points(card)

    def card_beats(self, view, card: int, other: int) -> bool:
        return dk.beats(card, other, second_dulle=self.p["second_dulle"])

    def allies(self, view: DoppelkopfView, player: int) -> set[int]:
        if view.is_re:
            return view.known_re - {player}
        if len(view.known_re) == 2:                  # both queens are out: the last seat is a partner
            return {x for x in range(dk.NUM_PLAYERS) if x != player and x not in view.known_re}
        return set()

    # --------------------------------------------------------------- policies
    def hanni_policy(self) -> Policy:
        return DoppelkopfBotPolicy("heuristic", name="Hanni Heuristic")

    def master_policy(self) -> Policy:
        return DoppelkopfBotPolicy("master", worlds=12, name="Master")

    @pick("lead-ace", "Lead a plain ace",
          "An ace of a plain suit is likely to take the first rounds. Lead one.", "star")
    def card_lead_ace(self, s, candidates, player, rng):
        if s.current_trick:
            return None
        aces = [c for c in candidates if dk.rank_of(c) == dk.ACE and not dk.is_trump(c)]
        return rng.choice(aces) if aces else None

    # ------------------------------------------------------------- presentation
    def action_label(self, s, a: Action) -> str:
        return card_name(int(a))

    def describe(self, s, a, player) -> str:
        return f"plays {card_name(int(a))}"

    def describe_chance(self, s, a) -> str:
        seat = len(s.history()) // dk.CARDS_PER_PLAYER
        return f"deals {card_name(int(a))} to {self.seat_label(seat)}"

    def describe_hidden(self, s, a, player) -> str:
        seat = len(s.history()) // dk.CARDS_PER_PLAYER
        return f"deals a card to {self.seat_label(seat)}"

    def status(self, s, viewer) -> str:
        if self.is_terminal(s):
            if viewer is None:
                return "Deal over"
            mine = self.returns(s)[viewer]
            verdict = "won" if mine > 0 else "lost" if mine < 0 else "drew"
            team = "Re" if viewer in s.re_players else "Kontra"
            return f"Deal over: you {verdict} as {team} ({mine:+g})"
        p = self.current_player(s)
        if p == CHANCE:
            return "Dealing the cards..."
        if viewer is not None and p == viewer:
            if not s.current_trick:
                return "Your turn: lead a card"
            led = s.current_trick[0]
            what = "trump" if dk.is_trump(led) else dk.SUIT_NAMES[dk.suit_of(led)].lower()
            return f"Your turn: follow {what}"
        return f"{self.seat_label(p)} to play"

    def card_entry(self, c: int, legal: bool = False) -> dict:
        return scene.playing_card(
            dk.RANK_LETTERS[dk.rank_of(c)], dk.SUIT_LETTERS[dk.suit_of(c)],
            action=c if legal else None, trump=dk.is_trump(c), points=dk.card_points(c) or None)

    def table_view(self, s, seat: int, spectating: bool) -> TableView:
        view = DoppelkopfView(s, seat)
        terminal = self.is_terminal(s)
        legal = set()
        if not terminal and self.current_player(s) == seat:
            legal = set(legal_cards(s.hands[seat], s.current_trick))
        trick = [self.entry(p, self.card_entry(c)) for p, c in view.trick]
        last = None
        if s.tricks:
            t = s.tricks[-1]
            last = {"winner": int(t.winner), "points": int(t.points),
                    "plays": [self.entry(t.player_of(i), self.card_entry(c))
                              for i, c in enumerate(t.cards)]}
        badges = [[] for _ in range(dk.NUM_PLAYERS)]
        revealed = set(s.re_players) if spectating or terminal else view.known_re
        for i in revealed:
            badges[i].append("Re")
        if spectating or terminal:
            for i in range(dk.NUM_PLAYERS):
                if i not in revealed:
                    badges[i].append("Kontra")
        elif view.is_re:
            badges[seat].append("Re")
        else:
            badges[seat].append("Kontra")
        extra = []
        if terminal:
            res = s.result()
            names = self.table_names(None if spectating else seat)
            extra.append(scene.kv([
                ("Re team", ", ".join(names[i] for i in sorted(s.re_players))),
                ("Re points", res["re_points"]), ("Kontra points", res["kontra_points"]),
                ("Game value (Re)", f"{res['value']:+d}"),
                ("Won", ", ".join(label for label, _ in res["base"])),
                ("Specials", ", ".join(label for label, _ in res["specials"]) or "none")],
                caption="Result"))
        hand = [self.card_entry(c, c in legal) for c in view.hand]
        return TableView(
            hand=hand, hand_sizes=[sum(h) for h in s.hands], trick=trick,
            leader=int(s.trick_leader) if s.current_trick else None, to_act=self.to_act(s),
            last_trick=last, taken=[int(x) for x in s.points_taken()], badges=badges,
            caption=f"Trick {min(len(s.tricks) + 1, dk.NUM_TRICKS)} of {dk.NUM_TRICKS}",
            extra_parts=extra)

    def all_hands(self, s) -> list[list[dict]]:
        out = []
        for seat in range(dk.NUM_PLAYERS):
            held = [c for c in range(dk.NUM_CARD_TYPES) for _ in range(s.hands[seat][c])]
            out.append([self.card_entry(c) for c in dk.sort_for_display(held)])
        return out
