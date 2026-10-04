"""Card tables: the shared home of every game played with hidden hands.

Kuhn poker, Skat and Doppelkopf look alike to the player: your cards at the
bottom, the others as card backs, a trick or a pot in the middle. This module
holds what they share, in two layers:

:class:`CardTableGame`
    Turns a small *view model* (:class:`TableView`) into a ``scene.table``.
    A game only describes what its seat sees, never how it is drawn. Also
    holds the seat names of the table and the hidden-information plumbing
    (who may see a dealt card).

:class:`TrickTakingGame`
    The family of Skat and Doppelkopf. Adds three rule cards that every
    trick-taking game shares ("Win it cheaply", "Feed your partner",
    "Dump the lowest"), written against four small hooks each game fills in.

Hidden information
------------------
``scene(s, viewer)`` shows the viewer's own hand and the public table only.
When ``viewer`` is ``None`` (a spectator who watches bots play) the scene is
omniscient: the table part gets one extra key, ``hands``, with the cards of
every seat face up. A view that does not know the key just ignores it::

    table["hands"] = [[<playing_card>, ...], ...]        # one list per seat

``table_view`` of a game must build everything from its viewer's seat. The
tests deal many games and check that the other seats' cards never appear in
a viewer's scene or observation.

Table seats
-----------
The viewer is always "You". The other seats get the names of
:attr:`CardTableGame.others`, clockwise starting at the viewer's left, which
is also where the page places them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Sequence

from strategy_lab.core import CHANCE, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.external import SpielGame


@dataclass
class TableView:
    """What one seat sees at a card table (everything optional but the hand).

    All card entries are :func:`~strategy_lab.core.scene.playing_card` dicts.
    A card in ``hand`` that carries an ``action`` is clickable.
    """

    hand: list[dict] = field(default_factory=list)
    hand_sizes: list[int] = field(default_factory=list)
    #: Cards on the table now: ``{"seat": s, "card": playing_card}``, in play order.
    trick: list[dict] = field(default_factory=list)
    leader: int | None = None
    to_act: int | None = None
    #: ``{"winner": seat, "points": n, "plays": [{"seat", "card"}, ...]}``
    last_trick: dict | None = None
    #: Card points collected per seat, if the game counts them openly.
    taken: list[int] | None = None
    #: Short tags per seat ("Re", "declarer").
    badges: list[list[str]] = field(default_factory=list)
    #: Open cards that belong to nobody (a skat, a board card).
    center: list[dict] = field(default_factory=list)
    caption: str = ""
    #: Actions that are not cards (bids, "pass"): ``(action, label)``.
    buttons: list[tuple[Action, str]] = field(default_factory=list)
    buttons_caption: str = ""
    #: Extra scene parts shown below (a result panel, chip counts).
    extra_parts: list[dict] = field(default_factory=list)


def strip_actions(card: dict) -> dict:
    """A copy of a card entry without its clickable action (for spectators)."""
    return {k: v for k, v in card.items() if k != "action"}


class CardTableGame(SpielGame):
    """OpenSpiel game with hidden hands drawn as a card table.

    Subclasses implement :meth:`table_view` (and :meth:`all_hands` if they
    want an omniscient spectator view) and keep everything else of
    :class:`~strategy_lab.families.external.SpielGame`.
    """

    #: Names of the other seats clockwise from the viewer's left.
    others: ClassVar[tuple[str, ...]] = ("Opponent",)
    chance_word = "Dealing"

    # ------------------------------------------------------------------ names
    def table_names(self, viewer: int | None) -> list[str]:
        """Display names per seat: "You" for the viewer, positions for the rest."""
        n = self.num_players
        if viewer is None:
            return [self.seat_label(i) for i in range(n)]
        return ["You" if i == viewer else self.others[(i - viewer - 1) % n]
                for i in range(n)]

    # ------------------------------------------------------------------ views
    def table_view(self, s: Any, seat: int, spectating: bool) -> TableView:
        """Build the view of ``seat``. ``spectating``: no clicks, nothing is hidden."""
        raise NotImplementedError

    def all_hands(self, s: Any) -> list[list[dict]]:
        """Every seat's hand as card entries (omniscient spectator view)."""
        raise NotImplementedError

    def scene(self, s: Any, viewer: int | None) -> dict:
        spectating = viewer is None
        seat = 0 if spectating else viewer
        view = self.table_view(s, seat, spectating)
        hand = [strip_actions(c) for c in view.hand] if spectating else view.hand
        part = scene.table(
            seat=seat, names=self.table_names(viewer), hand=hand,
            hand_sizes=view.hand_sizes, trick=view.trick, leader=view.leader,
            to_act=view.to_act, last_trick=view.last_trick, taken=view.taken,
            badges=view.badges, center=view.center, caption=view.caption)
        if spectating:
            part["hands"] = self.all_hands(s)
        parts = [part]
        if view.buttons and not spectating:
            parts.append(scene.buttons(view.buttons, caption=view.buttons_caption))
        parts.extend(view.extra_parts)
        return scene.scene(parts, status=self.status(s, viewer))

    # ------------------------------------------------------------------ small helpers
    @staticmethod
    def entry(seat: int, card: dict) -> dict:
        """One ``trick`` / ``plays`` entry."""
        return {"seat": seat, "card": card}

    def to_act(self, s: Any) -> int | None:
        """The seat that must decide now, or ``None`` at chance nodes and the end."""
        if self.is_terminal(s):
            return None
        p = self.current_player(s)
        return None if p == CHANCE else p


class TrickTakingGame(CardTableGame):
    """Family base of Skat and Doppelkopf: tricks, trumps, card points.

    Rule cards inherited by every trick-taking game. They read the game only
    through four hooks, and only what the acting seat can see:

    * :meth:`trick_view`: the seat's visible situation (any object),
    * :meth:`trick_so_far`: ``[(seat, card), ...]`` of the current trick,
    * :meth:`card_points` and :meth:`card_beats`,
    * :meth:`allies`: seats known to play on the same team.
    """

    family_id = "trick-taking"
    family_name = "Trick-taking games"
    family_blurb = ("Follow suit, win tricks, count points. The same rules of thumb "
                    "(win cheaply, feed your partner, dump the lowest) work in every "
                    "game of the family.")

    # ------------------------------------------------------------------ hooks
    def trick_view(self, s: Any, player: int) -> Any:
        """What ``player`` sees (a parsed observation). Must not peek at other hands."""
        raise NotImplementedError

    def trick_so_far(self, view: Any) -> list[tuple[int, int]]:
        """``(seat, card)`` of the cards already on the table, in play order."""
        raise NotImplementedError

    def card_points(self, card: int) -> int:
        """Card points of a card (what a trick is worth)."""
        raise NotImplementedError

    def card_beats(self, view: Any, card: int, other: int) -> bool:
        """Does ``card`` beat ``other`` (which is on the table) in the current trick?"""
        raise NotImplementedError

    def allies(self, view: Any, player: int) -> set[int]:
        """Seats that are known to be on ``player``'s team (without ``player``)."""
        return set()

    def is_card_action(self, a: Action) -> bool:
        """Is ``a`` a card (as opposed to a bid)? Games with bids override."""
        return True

    # ----------------------------------------------------------- shared logic
    def winning_play(self, view: Any) -> tuple[int, int] | None:
        """``(seat, card)`` that currently takes the trick, or ``None`` if it is empty."""
        best: tuple[int, int] | None = None
        for seat, card in self.trick_so_far(view):
            if best is None or self.card_beats(view, card, best[1]):
                best = (seat, card)
        return best

    def cards_among(self, candidates: Sequence[Action]) -> list[int]:
        return [int(a) for a in candidates if self.is_card_action(a)]

    @pick("cheap-win", "Win it cheaply",
          "If you can take the trick, do it with the least valuable card that wins. "
          "Unless a partner already has it.", "trophy")
    def card_cheap_win(self, s, candidates, player, rng):
        view = self.trick_view(s, player)
        best = self.winning_play(view)
        cards = self.cards_among(candidates)
        if best is None or len(cards) != len(candidates) or best[0] in self.allies(view, player):
            return None
        winners = [c for c in cards if self.card_beats(view, c, best[1])]
        if not winners:
            return None
        return min(winners, key=lambda c: (self.card_points(c), c))

    @pick("feed", "Feed your partner",
          "If a partner is winning the trick, add your most valuable card to it.", "handshake")
    def card_feed(self, s, candidates, player, rng):
        view = self.trick_view(s, player)
        best = self.winning_play(view)
        cards = self.cards_among(candidates)
        if best is None or len(cards) != len(candidates) or best[0] not in self.allies(view, player):
            return None
        return max(cards, key=lambda c: (self.card_points(c), -c))

    @pick("dump", "Dump the lowest",
          "When you do not take the trick, throw away the card worth the fewest points.",
          "scissors")
    def card_dump(self, s, candidates, player, rng):
        cards = self.cards_among(candidates)
        if not cards or len(cards) != len(candidates):
            return None
        return min(cards, key=lambda c: (self.card_points(c), c))
