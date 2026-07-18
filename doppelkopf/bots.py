"""A simple rule-based Doppelkopf bot for the CLI.

The bot only uses information a human player would have: its own hand,
the cards on the table, the public trick history, and team knowledge
inferred from played club queens (plus its own membership).
"""

import random

from doppelkopf import cards
from doppelkopf.game import legal_cards


class HeuristicBot:
  """Plays a reasonable normal game without card counting heroics."""

  def __init__(self, player, rng=None):
    self.player = player
    self.rng = rng or random.Random()

  def step(self, state):
    legal = legal_cards(state.hands[self.player], state.current_trick)
    if len(legal) == 1:
      return legal[0]
    if state.current_trick:
      return self._follow(state, legal)
    return self._lead(state, legal)

  # --- Leading a trick ---

  def _lead(self, state, legal):
    plain = [c for c in legal if not cards.is_trump(c)]
    trumps = [c for c in legal if cards.is_trump(c)]
    # Lead a plain ace: good odds to take the trick in the first rounds.
    aces = [c for c in plain if cards.rank_of(c) == cards.ACE]
    if aces:
      return self.rng.choice(aces)
    # With a strong trump holding, pull trumps.
    strong = [c for c in trumps if cards.trump_strength(c) >=
              cards.trump_strength(cards.CLUB_QUEEN) - 3]
    if len(trumps) >= 5 and strong:
      return max(strong, key=cards.trump_strength)
    # Otherwise lead something cheap.
    return self._cheapest(plain or legal)

  # --- Following in a trick ---

  def _follow(self, state, legal):
    trick = state.current_trick
    win_offset = cards.trick_winner_offset(trick)
    winning_seat = (state.trick_leader + win_offset) % cards.NUM_PLAYERS
    winning_card = trick[win_offset]
    trick_points = sum(cards.card_points(c) for c in trick)
    last_to_play = len(trick) == cards.NUM_PLAYERS - 1

    winners = [c for c in legal if cards.beats(c, winning_card)]

    if self._is_teammate(state, winning_seat):
      # Partner has the trick: feed it points ("schmieren"), or if the
      # partner's card is weak and the trick is fat, take over cheaply.
      if last_to_play or self._card_is_solid(winning_card):
        return self._fattest(legal)
      safe = [c for c in legal if not cards.beats(c, winning_card)]
      if trick_points >= 10 and winners:
        return self._cheapest_of_winners(winners)
      return self._fattest(safe) if safe else self._cheapest(legal)

    # Opponents (or unknown) hold the trick.
    if winners:
      worth_it = trick_points + 4 >= 10 or last_to_play
      if worth_it:
        return self._cheapest_of_winners(winners)
    return self._cheapest([c for c in legal if c not in winners] or legal)

  # --- Team knowledge ---

  def _is_teammate(self, state, seat):
    if seat == self.player:
      return True
    i_am_re = self.player in state.re_players
    known_re = state.known_re_players() | (
        state.re_players & {self.player})
    if i_am_re:
      return seat in known_re
    # As Kontra we only know Re seats for sure; everyone else might be
    # a partner, but assume opponent unless proven otherwise.
    return False

  # --- Card selection helpers ---

  def _cheapest(self, choices):
    return min(choices, key=lambda c: (cards.card_points(c),
                                       cards.trump_strength(c) or -1))

  def _fattest(self, choices):
    return max(choices, key=lambda c: (cards.card_points(c),
                                       -(cards.trump_strength(c) or 99)))

  def _cheapest_of_winners(self, winners):
    return min(winners, key=lambda c: (cards.trump_strength(c)
                                       if cards.is_trump(c) else -1,
                                       cards.card_points(c)))

  def _card_is_solid(self, card):
    """A card unlikely to be beaten later in the trick."""
    ts = cards.trump_strength(card)
    if ts is not None:
      return ts >= cards.trump_strength(cards.CLUB_QUEEN)
    return cards.rank_of(card) == cards.ACE
