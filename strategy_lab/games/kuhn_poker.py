"""Kuhn poker: the smallest poker game with a real bluff.

Three cards (Jack, Queen, King), two players, one chip each in the pot to
start, one round of betting. It is small enough to solve by hand and rich
enough to contain everything that makes poker hard: hidden cards, bluffing
and a *mixed* equilibrium.

The Nash bot uses the known equilibrium family from the Wikipedia article
"Kuhn poker" (https://en.wikipedia.org/wiki/Kuhn_poker). With a free
parameter ``alpha`` between 0 and 1/3, the first player

* with a Jack bets with probability ``alpha`` (a bluff) and folds to a bet,
* with a Queen checks, and calls a bet after checking with probability
  ``alpha + 1/3``,
* with a King bets with probability ``3 * alpha`` and always calls.

The second player has one equilibrium strategy: with a King always bet or
call, with a Queen check (after a check) and call a bet one time in three,
with a Jack bluff one time in three after a check and fold to a bet. The
tests check with OpenSpiel that the policy has exploitability 0, and that the
value of the game for the first player is -1/18 per hand.

Actions: 0 is *pass* (check, or fold when facing a bet) and 1 is *bet* (bet,
or call when facing a bet). The information state of a seat is its card
followed by the betting so far (``"1pb"``: a Queen that passed and faced a
bet), which is how the Nash policy looks up what to do.
"""

from __future__ import annotations

import pyspiel

from strategy_lab.core import CHANCE, Bot, Challenge, Model, Policy, Rulebook, pick, scene
from strategy_lab.core.game import Action
from strategy_lab.families.cards import CardTableGame, TableView

RANKS = ("J", "Q", "K")
PASS, BET = 0, 1
#: Chance node ids for the cards are 0 (Jack), 1 (Queen), 2 (King).
CARD_NAMES = {"J": "Jack", "Q": "Queen", "K": "King"}


def nash_bet_probabilities(alpha: float = 1 / 6) -> dict[str, float]:
    """``P(bet)`` per information state for the equilibrium with parameter ``alpha``.

    Keys are information-state strings: the card (0 Jack, 1 Queen, 2 King) and
    the betting so far (``p`` pass, ``b`` bet). ``alpha`` must lie in [0, 1/3].
    """
    if not 0.0 <= alpha <= 1 / 3:
        raise ValueError("alpha must be between 0 and 1/3")
    return {
        # first player, first decision
        "0": alpha, "1": 0.0, "2": 3 * alpha,
        # first player, facing a bet after checking
        "0pb": 0.0, "1pb": alpha + 1 / 3, "2pb": 1.0,
        # second player after a check
        "0p": 1 / 3, "1p": 0.0, "2p": 1.0,
        # second player facing a bet
        "0b": 0.0, "1b": 1 / 3, "2b": 1.0,
    }


class KuhnNashPolicy(Policy):
    """Plays the Nash equilibrium of Kuhn poker (a mixed strategy per information state)."""

    def __init__(self, alpha: float = 1 / 6, name: str = "nash"):
        self.alpha = alpha
        self.probabilities = nash_bet_probabilities(alpha)
        self.name = name

    def act(self, game, s, player, rng):
        p_bet = self.probabilities[game.observation(s, player)]
        return BET if rng.random() < p_bet else PASS

    def trace(self, game, s, player):
        info = game.observation(s, player)
        return {"info_state": info, "bet_probability": self.probabilities[info]}


class KuhnPoker(CardTableGame):
    id = "kuhn_poker"
    name = "Kuhn Poker"
    icon = "spade"
    tagline = "Three cards, one bet, and the smallest bluff in poker."
    chapter = "hidden"
    order = 10
    concepts = ("imperfect-information", "information-set", "bluffing", "mixed-strategy",
                "nash-equilibrium", "zero-sum")
    spiel_name = "kuhn_poker"
    seat_names = ("Player 1", "Player 2")
    others = ("Opponent",)
    max_steps = 20

    rulebook = Rulebook(
        summary="Two players, three cards: Jack, Queen, King. One hand, one round of "
                "betting, the higher card wins at showdown.",
        steps=(
            ("The ante", "Each player puts one chip in the pot and gets one card. You see "
                         "only your own."),
            ("Player 1 acts", "Check (pass) or bet one more chip."),
            ("Player 2 answers", "After a check: check too or bet. After a bet: call "
                                 "(add one chip) or fold."),
            ("A bet after a check", "If player 2 bets after a check, player 1 may still "
                                    "call or fold."),
            ("Showdown", "If nobody folded, the higher card takes the pot (King beats "
                         "Queen beats Jack). A player who folds loses the chips already in."),
        ),
        extra=(
            ("Buttons", "The same two actions change name with the situation: Pass is "
                        "Check or Fold, Bet is Bet or Call."),
            ("Showdown only", "The other player's card is shown only if there is a "
                              "showdown. After a fold it stays hidden."),
        ),
        source="https://en.wikipedia.org/wiki/Kuhn_poker",
    )

    models = (
        Model("hand", "Own card only", False,
              state="your card (J, Q or K)",
              size="3 states",
              actions="pass or bet",
              transition="the opponent answers; you do not see their card",
              reward="chips won or lost at the end of the hand (+-1, +-2); gamma = 1",
              note="Not Markov: the same card calls for different play after a check, "
                   "after a bet and when you act first. What was bet so far matters."),
        Model("infoset", "Card + betting history (information set)", True,
              state="your card plus the sequence of passes and bets so far",
              size="12 information sets (6 per player)",
              actions="pass or bet",
              transition="the opponent's reply depends on their hidden card, so from "
                         "your seat the next state is random",
              reward="chips won or lost at the end of the hand; gamma = 1",
              note="The information set OpenSpiel uses. With it the game is a tree you "
                   "can solve: the Nash equilibrium assigns one mix of actions to each "
                   "of the 12 sets."),
        Model("belief", "Information set + belief about their card", "approx",
              state="information set plus the probability that the opponent holds each "
                    "remaining card",
              size="a probability distribution per information set",
              actions="pass or bet",
              reward="expected chips; gamma = 1",
              note="A summary a human actually thinks in: 'they bet, so they probably "
                   "hold the King'. It is only as good as the opponent model behind it."),
    )

    bots = (
        Bot("randy", "Randy Rookie", "Passes or bets by coin flip, whatever he holds.",
            1, icon="dice"),
        Bot("bettina", "Bettina Bet", "Bets or calls every single time. Never folds.",
            2, cards=("always-bet",), icon="money"),
        Bot("hans", "Honest Hans", "Bets and calls only with a King. Never bluffs, never "
            "pays off.", 3, cards=("king", "meek"), icon="smile"),
        Bot("nora", "Nash Nora", "Plays the equilibrium: a Jack bluffs one time in six, a "
            "King bets half the time. You cannot exploit her.", 4,
            policy="nora_policy", icon="scale"),
    )

    challenges = (
        Challenge("finish", "Play a hand to the end", "finish"),
        Challenge("beat-bettina", "Beat Bettina Bet", "win", 1, bot="bettina"),
        Challenge("big-pot", "Win 2 chips off Bettina Bet", "score", 1, bot="bettina", value=2.0),
        Challenge("beat-hans", "Beat Honest Hans (bluff him)", "win", 2, bot="hans"),
        Challenge("nash", "Open the equilibrium lens", "lens", 2, lens="nash"),
        Challenge("beat-nora", "Beat Nash Nora", "win", 3, bot="nora"),
    )

    # ------------------------------------------------------------------ parsing
    def deals(self, s: pyspiel.State) -> list[int]:
        """The card (0..2) of every seat that has one so far."""
        return [int(c) for c in s.history()[:2]]

    def betting(self, s: pyspiel.State) -> list[int]:
        """The actions (0 pass, 1 bet) taken so far."""
        return [int(a) for a in s.history()[2:]]

    def contributions(self, s: pyspiel.State) -> list[int]:
        """Chips each seat has put in, antes included."""
        chips = [1, 1]
        for i, a in enumerate(self.betting(s)):
            if a == BET:
                chips[i % 2] += 1
        return chips

    def facing_bet(self, s: pyspiel.State) -> bool:
        acts = self.betting(s)
        return bool(acts) and acts[-1] == BET

    def showdown(self, s: pyspiel.State) -> bool:
        """Did the hand end with both cards shown (no fold)?"""
        acts = self.betting(s)
        return self.is_terminal(s) and (acts[-1] == BET and len(acts) >= 2
                                        and acts[-2] == BET or acts == [PASS, PASS])

    # ------------------------------------------------------------- presentation
    def action_label(self, s: pyspiel.State, a: Action) -> str:
        if s.current_player() == CHANCE:
            return RANKS[int(a)]
        if self.facing_bet(s):
            return "Call" if int(a) == BET else "Fold"
        return "Bet" if int(a) == BET else "Check"

    def describe(self, s, a, player) -> str:
        return {"Call": "calls", "Fold": "folds", "Bet": "bets", "Check": "checks"}[
            self.action_label(s, a)]

    def describe_chance(self, s, a) -> str:
        seat = len(s.history())          # the first deal is for seat 0, the second for seat 1
        return f"deals the {CARD_NAMES[RANKS[int(a)]]} to {self.seat_label(seat)}"

    def status(self, s, viewer) -> str:
        if self.is_terminal(s):
            if viewer is None:
                return "Hand over"
            won = self.returns(s)[viewer]
            how = "showdown" if self.showdown(s) else "a fold"
            chips = f"{abs(won):g} chip" + ("" if abs(won) == 1 else "s")
            return f"{'You win' if won > 0 else 'You lose'} {chips} after {how}"
        p = self.current_player(s)
        if p == CHANCE:
            return "Dealing the cards..."
        who = "Your move" if viewer == p else f"{self.seat_label(p)} to act"
        return f"{who}: call or fold?" if self.facing_bet(s) else f"{who}: check or bet?"

    @staticmethod
    def kuhn_card(rank: int, action: Action | None = None) -> dict:
        return scene.playing_card(RANKS[rank], "S", action=action)

    def table_view(self, s: pyspiel.State, seat: int, spectating: bool) -> TableView:
        dealt = self.deals(s)
        chips = self.contributions(s)
        hand = [self.kuhn_card(dealt[seat])] if seat < len(dealt) else []
        trick = []
        if self.is_terminal(s) and (self.showdown(s) or spectating):
            trick = [self.entry(i, self.kuhn_card(c)) for i, c in enumerate(dealt)]
        buttons = []
        if not self.is_terminal(s) and self.current_player(s) == seat:
            buttons = [(a, self.action_label(s, a)) for a in self.legal_actions(s)]
        pot = sum(chips)
        you, other = chips[seat], chips[1 - seat]
        panel = scene.kv([("Pot", pot), ("You put in", you), ("Opponent put in", other)],
                         caption="Chips")
        return TableView(
            hand=hand, hand_sizes=[min(len(dealt), 1) if i < len(dealt) else 0 for i in range(2)],
            trick=trick, to_act=self.to_act(s), caption=f"Pot: {pot} chips",
            buttons=buttons, buttons_caption="Your decision", extra_parts=[panel])

    def all_hands(self, s: pyspiel.State) -> list[list[dict]]:
        return [[self.kuhn_card(c)] for c in self.deals(s)] + [[] for _ in range(2 - len(self.deals(s)))]

    # --------------------------------------------------------------- hidden info
    def sample_world(self, s, player, rng):
        """The opponent's card is the only hidden fact: draw it from the unseen cards."""
        own = int(s.history()[player])
        unseen = [c for c in range(3) if c != own]
        world = self.initial_state()
        cards = [0, 0]
        cards[player] = own
        cards[1 - player] = rng.choice(unseen)
        for c in cards:
            world.apply_action(c)
        for a in s.history()[2:]:
            world.apply_action(int(a))
        return world

    # ------------------------------------------------------------------- policies
    def nora_policy(self) -> Policy:
        return KuhnNashPolicy(1 / 6, name="Nash Nora")

    def _context(self, s, player) -> tuple[int, str]:
        """``(card, betting so far)`` from the seat's own information state."""
        info = self.observation(s, player)
        return int(info[0]), info[1:]

    @pick("king", "Bet or call with the King",
          "The King wins every showdown. Put chips in.", "crown")
    def card_king(self, s, candidates, player, rng):
        card, _ = self._context(s, player)
        return BET if card == 2 else None

    @pick("fold-jack", "Fold a Jack to a bet",
          "A Jack can only win if the other player is bluffing.", "barrier")
    def card_fold_jack(self, s, candidates, player, rng):
        card, bets = self._context(s, player)
        return PASS if card == 0 and bets.endswith("b") else None

    @pick("check-queen", "Check the Queen",
          "A Queen beats only a Jack. Betting it mostly gets called by Kings.", "mirror")
    def card_check_queen(self, s, candidates, player, rng):
        card, bets = self._context(s, player)
        return PASS if card == 1 and not bets.endswith("b") else None

    @pick("bluff-jack", "Bluff with a Jack one time in three",
          "A Jack never wins a showdown, but a bet can win the pot. Do it now and then, "
          "so a bet from you is not a sure King.", "sparkle")
    def card_bluff_jack(self, s, candidates, player, rng):
        card, bets = self._context(s, player)
        if card == 0 and not bets.endswith("b"):
            return BET if rng.random() < 1 / 3 else PASS
        return None

    @pick("call-queen", "Call with a Queen one time in three",
          "Facing a bet, a Queen beats only a bluff. Call just often enough that bluffing "
          "does not pay.", "scale")
    def card_call_queen(self, s, candidates, player, rng):
        card, bets = self._context(s, player)
        if card == 1 and bets.endswith("b"):
            return BET if rng.random() < 1 / 3 else PASS
        return None

    @pick("always-bet", "Always bet", "Bet or call, whatever the card.", "money")
    def card_always_bet(self, s, candidates, player, rng):
        return BET

    @pick("meek", "Check or fold", "Never put another chip in.", "snowflake")
    def card_meek(self, s, candidates, player, rng):
        return PASS
