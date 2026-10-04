"""Skat on the OpenSpiel engine (three players, one against two).

OpenSpiel's Skat is *slightly simplified* (its header says so: "Currently the
bidding is vastly simplified. The players are allowed to make bids or not in
order. The first player who makes a bid is the solo player. Allowed bids are
only the 6 game types"). There is no numeric bidding, no Hand or Ouvert game,
and the score is linear in the card points: ``(points - 60) / 120`` for the
declarer and ``(points - 60) / 240`` for each defender.

Reading the game
----------------
``str(state)`` prints every hand, so it is never used. Everything a seat
knows is decoded from OpenSpiel's *observation tensor* of that seat (the
engine builds its observation string from the same tensor)::

    [0:3]    seat            [3:6]    phase flags (bidding, discarding, playing)
    [6:38]   own cards       [38:59]  bids, 3 seats x 7 game types
    [59:62]  declarer        [62:94]  the skat (declarer only, after discarding)
    [94:101] game type       [101:104] leader of the current trick
    [104:200] current trick, 3 plays x 32 cards, in play order
    [200:203] leader of the previous trick   [203:299] previous trick

Cards are ``suit * 8 + rank`` with suits diamonds, hearts, spades, clubs and
ranks 7, 8, 9, Q, K, 10, A, J. Actions 0..31 are cards (dealing, discarding,
playing), actions 32..38 are the bids: pass, the four suits, grand, null.

The only line read from the full state is the public tally ``Points (Solo /
Team)`` and the winner of the last trick, which every player may see.

Hand sizes of the other seats are derived from public facts, the same way a
player counts cards at the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pyspiel

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Rulebook, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.cards import TableView, TrickTakingGame

NUM_CARDS = 32
BID_BASE = 32
SUIT_LETTERS = "DHSC"                       # engine order: diamonds, hearts, spades, clubs
RANK_NAMES = ("7", "8", "9", "Q", "K", "10", "A", "J")
RANK_POINTS = (0, 0, 0, 3, 4, 10, 11, 2)
JACK, ACE, TEN = 7, 6, 5
SYMBOL = {"D": "\N{BLACK DIAMOND SUIT}", "H": "\N{BLACK HEART SUIT}",
          "S": "\N{BLACK SPADE SUIT}", "C": "\N{BLACK CLUB SUIT}"}
GAME_NAMES = ("none", "diamonds", "hearts", "spades", "clubs", "grand", "null")
BID_LABELS = ("Pass", "Diamonds", "Hearts", "Spades", "Clubs", "Grand", "Null")
#: Order of the plain cards in a trick (null games use ``NULL_ORDER``).
NULL_ORDER = {0: 0, 1: 1, 2: 2, 5: 3, 7: 4, 3: 5, 4: 6, 6: 7}
#: Who gets the card of deal round ``r``: a seat, or -1 for the skat (official order).
DEAL_ORDER = tuple(
    next((seat for seat, rounds in enumerate(
        ((*range(0, 3), *range(11, 15), *range(23, 26)),
         (*range(3, 6), *range(15, 19), *range(26, 29)),
         (*range(6, 9), *range(19, 23), *range(29, 32)))) if r in rounds), -1)
    for r in range(NUM_CARDS))
_POINTS = re.compile(r"Points \(Solo / Team\): \((\d+) / (\d+)\)")
_LAST_WINNER = re.compile(r"Last trick won by player (-?\d+)")


def suit_of(card: int) -> int:
    return card // 8


def rank_of(card: int) -> int:
    return card % 8


def card_name(card: int) -> str:
    """Display name such as ``"\N{BLACK HEART SUIT}Q"`` (suit symbol and rank)."""
    return SYMBOL[SUIT_LETTERS[suit_of(card)]] + RANK_NAMES[rank_of(card)]


def is_trump(card: int, game: int) -> bool:
    """Jacks are trump in every game but null; in a suit game so is the whole suit."""
    if game == 6:
        return False
    if rank_of(card) == JACK:
        return True
    return 1 <= game <= 4 and suit_of(card) == game - 1


def trick_order(card: int, first: int, game: int) -> int:
    """Strength of ``card`` in a trick led with ``first`` (-1: cannot win). Mirrors OpenSpiel."""
    if is_trump(card, game):
        return 7 + (suit_of(card) + JACK if rank_of(card) == JACK else rank_of(card))
    if suit_of(card) == suit_of(first):
        return NULL_ORDER[rank_of(card)] if game == 6 else rank_of(card)
    return -1


def hand_sort_key(card: int, game: int):
    """Display order: trumps strongest first, then the plain suits."""
    if is_trump(card, game):
        return (0, -trick_order(card, card, game))
    return (1 + suit_of(card), -(NULL_ORDER[rank_of(card)] if game == 6 else rank_of(card)))


@dataclass
class SkatView:
    """One seat's decoded observation. See the module docstring for the layout."""

    seat: int = 0
    phase: str = "dealing"                  # dealing, bidding, discarding, playing, over
    hand: list[int] = field(default_factory=list)
    bids: list[int] = field(default_factory=lambda: [0, 0, 0])
    solo: int = -1
    skat: list[int] = field(default_factory=list)
    game: int = 0
    trick_leader: int = -1
    trick: list[int] = field(default_factory=list)
    prev_leader: int = -1
    prev: list[int] = field(default_factory=list)

    def trick_plays(self) -> list[tuple[int, int]]:
        return [((self.trick_leader + i) % 3, c) for i, c in enumerate(self.trick)]

    def prev_plays(self) -> list[tuple[int, int]]:
        return [((self.prev_leader + i) % 3, c) for i, c in enumerate(self.prev)]


def parse_view(t) -> SkatView:
    """Decode an observation tensor."""
    def cards(offset: int) -> list[int]:
        return [c for c in range(NUM_CARDS) if t[offset + c]]

    def one_hot(offset: int, n: int) -> int:
        return next((i for i in range(n) if t[offset + i]), -1)

    if not any(t):
        return SkatView()
    phase = ("bidding" if t[3] else "discarding" if t[4] else "playing" if t[5] else "over")
    view = SkatView(
        seat=one_hot(0, 3), phase=phase, hand=cards(6),
        bids=[max(0, one_hot(38 + 7 * i, 7)) for i in range(3)],
        solo=one_hot(59, 3), skat=cards(62), game=max(0, one_hot(94, 7)))
    view.trick_leader = one_hot(101, 3)
    view.trick = [next((c for c in range(NUM_CARDS) if t[104 + 32 * i + c]), -1) for i in range(3)]
    view.trick = [c for c in view.trick if c >= 0]
    view.prev_leader = one_hot(200, 3)
    view.prev = [next((c for c in range(NUM_CARDS) if t[203 + 32 * i + c]), -1) for i in range(3)]
    view.prev = [c for c in view.prev if c >= 0]
    return view


def best_suit(hand: list[int]) -> tuple[int, int]:
    """``(game type 1..4, number of trumps)`` of the suit game that suits ``hand`` best."""
    best = (1, -1)
    for game in range(1, 5):
        trumps = [c for c in hand if is_trump(c, game)]
        side_aces = sum(1 for c in hand if not is_trump(c, game) and rank_of(c) == ACE)
        score = len(trumps) + 0.5 * side_aces
        if score > best[1]:
            best = (game, score)
    return best[0], int(best[1])


def strong_game(hand: list[int]) -> int:
    """The game type worth declaring with ``hand``, or 0 (pass)."""
    jacks = [c for c in hand if rank_of(c) == JACK]
    aces = sum(1 for c in hand if rank_of(c) == ACE)
    if len(jacks) >= 3 and aces >= 2:
        return 5
    game, strength = best_suit(hand)
    return game if strength >= 6 else 0


class Skat(TrickTakingGame):
    id = "skat"
    name = "Skat"
    icon = "cards"
    tagline = "Three players, one against two, and a skat nobody has seen."
    chapter = "hidden"
    order = 20
    concepts = ("imperfect-information", "information-set", "belief", "rule-cards", "heuristic")
    spiel_name = "skat"
    seat_names = ("South", "West", "East")
    others = ("West", "East")
    max_steps = 90

    rulebook = Rulebook(
        summary="A three-player German trick game: one declarer against two defenders.",
        steps=(
            ("Deal and bidding", "Each player gets ten cards, two go face down into the "
                                 "skat. In turn each player passes or names a game: a trump "
                                 "suit, grand (only jacks are trump) or null (no trumps, "
                                 "avoid every trick). The first to name a game becomes the "
                                 "declarer."),
            ("The skat", "The declarer picks up the skat and discards two cards face down. "
                         "Their card points count for the declarer."),
            ("Playing", "Ten tricks. Follow suit (or trump) if you can. The winner of a "
                        "trick leads the next one. Card points: ace 11, ten 10, king 4, "
                        "queen 3, jack 2."),
            ("Winning", "The declarer needs 61 of the 120 card points. The two defenders "
                        "together try to keep the declarer below that. In a null game the "
                        "declarer wins by taking no trick at all."),
        ),
        extra=(
            ("Simplified by OpenSpiel", "The engine's header says: \"A slightly simplified "
                                        "version of Skat ... Currently the bidding is vastly "
                                        "simplified. The players are allowed to make bids or "
                                        "not in order. The first player who makes a bid is "
                                        "the solo player. Allowed bids are only the 6 game "
                                        "types. This means Hand and Ouvert games are currently "
                                        "not implemented.\" "
                                        "(open_spiel/games/skat/skat.h)"),
            ("Scoring", "The return is (declarer points - 60) / 120 for the declarer and "
                        "(defender points - 60) / 240 for each defender, so it is zero-sum. "
                        "If everyone passes nobody plays and everyone gets 0."),
            ("Who leads", "Seat 0 leads the first trick, not the declarer."),
        ),
        source="https://www.pagat.com/schafkopf/skat.html",
    )

    models = (
        Model("hand-trick", "Own hand + current trick", False,
              state="your own hand plus the cards on the table in this trick",
              actions="legal cards to play (you must follow suit if you can)",
              reward="card points, turned into the declarer's or defenders' score",
              note="Cheap to track, but blind to the game: you cannot count points or "
                   "tell who has already run out of a suit."),
        Model("hand-trick-played", "Own hand + trick + all cards played", "approx",
              state="own hand + current trick + every card played in earlier tricks "
                    "(card counting)",
              actions="legal cards to play (you must follow suit if you can)",
              reward="card points, turned into the declarer's or defenders' score",
              note="Lets you count the remaining points and cards, but drops who played "
                   "which card and the bidding, so it cannot fully use inference about "
                   "the hidden hands."),
        Model("info-set", "Full information set (bidding + play history)", True,
              state="the entire observed history: the auction, the declared game, the "
                    "skat pickup if any, and every card played, in order and by whom",
              size="astronomically many, but it is the only state that predicts the "
                   "future of a hidden-information game",
              actions="bids and declarations during the auction, then one legal card "
                      "per trick",
              transition="the two hidden hands make every move of the others uncertain; "
                         "from your seat the opponents are part of the environment",
              reward="card points, turned into the declarer's or defenders' score",
              note="This is the information state OpenSpiel's algorithms work on. It is "
                   "large and grows through the deal."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Names a game and plays cards at random. Passes out "
            "a lot of good hands.", 1, icon="dice"),
        Bot("sepp", "Sepp", "Always names his longest suit, then simply throws away his "
            "lowest card every trick.", 2, cards=("bid-any", "skat-dump", "dump"),
            icon="smile"),
        Bot("heidi", "Heidi", "Bids only with a real hand, never lets the deal pass out, "
            "takes tricks cheaply and feeds her partner.", 3,
            cards=("bid-strong", "bid-last", "pass-weak", "skat-dump", "pull-trumps",
                   "cheap-win", "feed", "dump"), icon="shield"),
        Bot("gerd", "Gerd the Counter", "Heidi's rules plus cashing aces as a defender.", 3,
            cards=("bid-strong", "bid-last", "pass-weak", "skat-dump", "pull-trumps",
                   "cheap-win", "feed", "cash-ace", "dump"), icon="brain"),
    )

    challenges = (
        Challenge("finish", "Play a deal to the end", "finish"),
        Challenge("belief", "Open the belief lens", "lens", 1, lens="belief"),
        Challenge("beat-sepp", "Beat Sepp", "win", 1, bot="sepp"),
        Challenge("beat-heidi", "Beat Heidi", "win", 2, bot="heidi"),
        Challenge("beat-gerd", "Beat Gerd the Counter", "win", 3, bot="gerd"),
    )

    # ----------------------------------------------------------------- parsing
    def view_of(self, s: pyspiel.State, seat: int) -> SkatView:
        return parse_view(s.observation_tensor(seat))

    def trick_view(self, s, player) -> SkatView:
        return self.view_of(s, player)

    def trick_so_far(self, view: SkatView):
        return view.trick_plays()

    def card_points(self, card: int) -> int:
        return RANK_POINTS[rank_of(card)]

    def card_beats(self, view: SkatView, card: int, other: int) -> bool:
        first = view.trick[0]
        return trick_order(card, first, view.game) > trick_order(other, first, view.game)

    def allies(self, view: SkatView, player: int) -> set[int]:
        if view.solo < 0 or player == view.solo:
            return set()
        return {x for x in range(3) if x not in (player, view.solo)}

    def is_card_action(self, a: Action) -> bool:
        return int(a) < NUM_CARDS

    def tally(self, s: pyspiel.State) -> tuple[int, int, int]:
        """Public ``(declarer points, defender points, winner of the last trick)``."""
        text = str(s)
        points = _POINTS.search(text)
        winner = _LAST_WINNER.search(text)
        return (int(points.group(1)) if points else 0, int(points.group(2)) if points else 0,
                int(winner.group(1)) if winner else -1)

    def hand_sizes(self, s: pyspiel.State, view: SkatView) -> list[int]:
        """Cards in every seat's hand, from public facts only."""
        if view.phase in ("dealing", "over"):
            return [0, 0, 0] if view.phase == "over" else [10, 10, 10]
        if view.phase == "bidding":
            return [10, 10, 10]
        if view.phase == "discarding":
            discards = sum(1 for a in s.history()[NUM_CARDS:] if a < NUM_CARDS)
            return [12 - discards if i == view.solo else 10 for i in range(3)]
        played_now = {seat for seat, _ in view.trick_plays()}
        done = 10 - len(view.hand) - (1 if view.seat in played_now else 0)
        return [10 - done - (1 if i in played_now else 0) for i in range(3)]

    # --------------------------------------------------------------- hidden info
    def chance_audience(self, s, a):
        """Deal rounds follow the official order; the skat is seen by nobody."""
        recipient = DEAL_ORDER[len(s.history())]
        return () if recipient < 0 else (recipient,)

    def privacy(self, s, a, player):
        if player == CHANCE:
            return self.chance_audience(s, a)
        if self.view_of(s, player).phase == "discarding":
            return (player,)
        return None

    def describe_hidden(self, s, a, player) -> str:
        if player == CHANCE:
            audience = self.chance_audience(s, a)
            if audience == ():
                return "puts a card into the skat"
            return f"deals a card to {self.seat_label(audience[0])}"
        return "discards a card to the skat"

    # ------------------------------------------------------------- presentation
    def action_label(self, s: pyspiel.State, a: Action) -> str:
        a = int(a)
        return card_name(a) if a < NUM_CARDS else BID_LABELS[a - BID_BASE]

    def describe(self, s, a, player) -> str:
        a = int(a)
        if a >= NUM_CARDS:
            return "passes" if a == BID_BASE else f"names {GAME_NAMES[a - BID_BASE]}"
        if self.view_of(s, player).phase == "discarding":
            return f"discards {card_name(a)} to the skat"
        return f"plays {card_name(a)}"

    def describe_chance(self, s, a) -> str:
        recipient = DEAL_ORDER[len(s.history())]
        target = "the skat" if recipient < 0 else self.seat_label(recipient)
        return f"deals {card_name(int(a))} to {target}"

    def status(self, s, viewer) -> str:
        if self.is_terminal(s):
            solo = self.view_of(s, 0).solo
            if solo < 0:
                return "Everyone passed: no game"
            ret = self.returns(s)
            who = self.seat_label(solo)
            if viewer is None:
                return f"Deal over: {who} declared"
            mine = ret[viewer]
            verdict = "won" if mine > 0 else "lost" if mine < 0 else "drew"
            role = "declarer" if viewer == solo else "defender"
            return f"Deal over: you {verdict} as {role}"
        p = self.current_player(s)
        if p == CHANCE:
            return "Dealing the cards..."
        phase = self.view_of(s, p).phase
        mine = viewer == p
        who = "You" if mine else self.seat_label(p)
        if phase == "bidding":
            return "Bidding: name a game or pass" if mine else f"{who} is bidding"
        if phase == "discarding":
            return "Discard two cards to the skat" if mine else f"{who} discards to the skat"
        return "Your turn to play" if mine else f"{who} to play"

    def table_view(self, s: pyspiel.State, seat: int, spectating: bool) -> TableView:
        view = self.view_of(s, seat)
        game = view.game
        known = game != 0
        terminal = self.is_terminal(s)
        mover = self.current_player(s)
        legal = set(self.legal_actions(s)) if not terminal and mover == seat else set()

        def card(c: int, with_action: bool = False) -> dict:
            return scene.playing_card(
                RANK_NAMES[rank_of(c)], SUIT_LETTERS[suit_of(c)],
                action=c if with_action and c in legal else None,
                trump=known and is_trump(c, game), points=RANK_POINTS[rank_of(c)] or None)

        hand = [card(c, True) for c in sorted(view.hand, key=lambda c: hand_sort_key(c, game))]
        trick = [self.entry(p, card(c)) for p, c in view.trick_plays()]
        last = None
        if view.prev:
            _, _, winner = self.tally(s)
            plays = [self.entry(p, card(c)) for p, c in view.prev_plays()]
            last = {"winner": winner if winner >= 0 else view.trick_leader,
                    "points": sum(RANK_POINTS[rank_of(c)] for c in view.prev), "plays": plays}
        badges: list[list[str]] = [[] for _ in range(3)]
        if view.solo >= 0:
            badges[view.solo] += ["declarer", GAME_NAMES[game]]
        elif view.phase == "bidding":
            for i, bid in enumerate(view.bids):
                if bid == 0 and i < mover:
                    badges[i].append("passed")
        center = []
        if view.skat:
            center = [card(c) for c in view.skat]
        elif view.phase in ("bidding", "discarding", "dealing"):
            center = [scene.playing_card("?", "S", faceup=False)] * 2
        solo_pts, team_pts, _ = self.tally(s) if view.phase in ("playing", "over") else (0, 0, -1)
        taken = None
        if view.solo >= 0 and view.phase in ("playing", "over"):
            taken = [solo_pts if i == view.solo else team_pts for i in range(3)]
        buttons = []
        if view.phase == "bidding" and BID_BASE in legal:
            buttons = [(a, self.action_label(s, a)) for a in sorted(legal)]
        caption = {"bidding": "Bidding: the first player to name a game becomes the declarer",
                   "discarding": "Discard two cards to the skat",
                   "playing": f"{GAME_NAMES[game].capitalize()} game: declarer {solo_pts}, "
                              f"defenders {team_pts}"}.get(view.phase, "")
        extra = []
        if terminal and view.solo >= 0:
            ret = self.returns(s)
            extra.append(scene.kv([
                ("Game", GAME_NAMES[game].capitalize()),
                ("Declarer", self.table_names(None if spectating else seat)[view.solo]),
                ("Declarer points", solo_pts), ("Defender points", team_pts),
                ("Score of the declarer", f"{ret[view.solo]:+.3f}")], caption="Result"))
        return TableView(
            hand=hand, hand_sizes=self.hand_sizes(s, view), trick=trick,
            leader=view.trick_leader if view.trick else None, to_act=self.to_act(s),
            last_trick=last, taken=taken, badges=badges, center=center, caption=caption,
            buttons=buttons, buttons_caption="Name a game or pass", extra_parts=extra)

    def all_hands(self, s: pyspiel.State) -> list[list[dict]]:
        """Omniscient view for spectators: parsed from the engine's full state string."""
        game = self.view_of(s, 0).game
        lines = {int(m.group(1)): m.group(2) for m in re.finditer(r"Player (\d): (.*)", str(s))}
        hands = []
        for seat in range(3):
            cards = self._glyph_cards(lines.get(seat, ""))
            cards.sort(key=lambda c: hand_sort_key(c, game))
            hands.append([scene.playing_card(RANK_NAMES[rank_of(c)], SUIT_LETTERS[suit_of(c)],
                                             trump=game != 0 and is_trump(c, game),
                                             points=RANK_POINTS[rank_of(c)] or None)
                          for c in cards])
        return hands

    @staticmethod
    def _glyph_cards(text: str) -> list[int]:
        """Decode the playing-card glyphs of a hand line into card ids."""
        rows = {0xA: "S", 0xB: "H", 0xC: "D", 0xD: "C"}
        nibbles = {0x1: 6, 0x7: 0, 0x8: 1, 0x9: 2, 0xA: 5, 0xB: 7, 0xD: 3, 0xE: 4}
        out = []
        for ch in text.split():
            off = ord(ch) - 0x1F0A0
            row, nib = off // 16 + 0xA, off % 16
            if row in rows and nib in nibbles:
                out.append(SUIT_LETTERS.index(rows[row]) * 8 + nibbles[nib])
        return out

    # --------------------------------------------------------------------- cards
    def _phase(self, s, player) -> str:
        return self.view_of(s, player).phase

    @pick("bid-strong", "Bid with a real hand",
          "Name a game when you hold three jacks and aces, or six or more trumps.", "crown")
    def card_bid_strong(self, s, candidates, player, rng):
        view = self.view_of(s, player)
        if view.phase != "bidding":
            return None
        game = strong_game(view.hand)
        return BID_BASE + game if game and BID_BASE + game in candidates else None

    @pick("bid-last", "Never pass the deal out",
          "If you are the last to bid and both others passed, name your best suit anyway.",
          "flag")
    def card_bid_last(self, s, candidates, player, rng):
        view = self.view_of(s, player)
        if view.phase != "bidding" or player != 2:
            return None
        return BID_BASE + best_suit(view.hand)[0]

    @pick("bid-any", "Always name your longest suit",
          "Whatever you hold, declare the suit you have most trumps in.", "sparkle")
    def card_bid_any(self, s, candidates, player, rng):
        view = self.view_of(s, player)
        return BID_BASE + best_suit(view.hand)[0] if view.phase == "bidding" else None

    @pick("pass-weak", "Pass with a weak hand", "No game worth naming: pass.", "snowflake")
    def card_pass_weak(self, s, candidates, player, rng):
        return BID_BASE if self._phase(s, player) == "bidding" else None

    @pick("skat-dump", "Discard from your weakest side suit",
          "Put the two lowest non-trump cards into the skat, emptying a short suit first.",
          "scissors")
    def card_skat_dump(self, s, candidates, player, rng):
        view = self.view_of(s, player)
        if view.phase != "discarding":
            return None
        side = [c for c in candidates if not is_trump(c, view.game)] or list(candidates)
        length = {su: sum(1 for c in view.hand if suit_of(c) == su) for su in range(4)}
        return min(side, key=lambda c: (RANK_POINTS[rank_of(c)], length[suit_of(c)], c))

    @pick("pull-trumps", "Pull the trumps",
          "As declarer, lead your highest trump while you have one.", "mountain")
    def card_pull_trumps(self, s, candidates, player, rng):
        view = self.view_of(s, player)
        if view.phase != "playing" or view.trick or player != view.solo:
            return None
        trumps = [c for c in candidates if is_trump(c, view.game)]
        return max(trumps, key=lambda c: trick_order(c, c, view.game)) if trumps else None

    @pick("cash-ace", "Cash your aces",
          "As a defender, lead a plain ace before someone trumps it.", "money")
    def card_cash_ace(self, s, candidates, player, rng):
        view = self.view_of(s, player)
        if view.phase != "playing" or view.trick or player == view.solo:
            return None
        aces = [c for c in candidates if rank_of(c) == ACE and not is_trump(c, view.game)]
        return aces[0] if aces else None
