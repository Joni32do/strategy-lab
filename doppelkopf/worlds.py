"""Determinization for Doppelkopf: sampling worlds consistent with a view.

A "world" is a fully determined game position: every hidden hand filled
in. Sampling worlds that are consistent with everything a player has
observed (cards played, follow-suit failures, own hand) is the basis of
the perfect-information Monte Carlo search in `search.py`.

Also provides `LightState`, a minimal fast simulator with the same play
dynamics as the OpenSpiel state in `game.py` (hands as per-type counts,
tricks, follow-suit rule) but without any engine overhead, so rollouts
are cheap. It exposes the attributes the heuristic bot reads
(`hands`, `current_trick`, `trick_leader`, `tricks`, `re_players`,
`known_re_players()`), so `HeuristicBot` runs on it unchanged.
"""

import random

from doppelkopf import cards
from doppelkopf import scoring
from doppelkopf.game import legal_cards


class LightState:
  """A fast, plain-Python mirror of DoppelkopfState's play phase."""

  __slots__ = ("hands", "trick_leader", "current_trick", "tricks",
               "re_players")

  def __init__(self, hands, trick_leader, current_trick, tricks, re_players):
    self.hands = [list(h) for h in hands]
    self.trick_leader = trick_leader
    self.current_trick = list(current_trick)
    self.tricks = list(tricks)
    self.re_players = set(re_players)

  @classmethod
  def from_state(cls, state):
    """Copies any state-like object (DoppelkopfState or LightState)."""
    return cls(state.hands, state.trick_leader, state.current_trick,
               state.tricks, state.re_players)

  def clone(self):
    return LightState.from_state(self)

  def is_terminal(self):
    return len(self.tricks) == cards.NUM_TRICKS

  def current_player(self):
    return (self.trick_leader + len(self.current_trick)) % cards.NUM_PLAYERS

  def legal_actions(self):
    return legal_cards(self.hands[self.current_player()], self.current_trick)

  def apply_action(self, card):
    player = self.current_player()
    assert self.hands[player][card] > 0
    self.hands[player][card] -= 1
    self.current_trick.append(card)
    if len(self.current_trick) == cards.NUM_PLAYERS:
      trick = scoring.Trick(self.trick_leader, self.current_trick)
      self.tricks.append(trick)
      self.trick_leader = trick.winner
      self.current_trick = []

  def returns(self):
    assert self.is_terminal()
    return scoring.compute_result(self.re_players, self.tricks)["returns"]

  def points_taken(self):
    taken = [0] * cards.NUM_PLAYERS
    for t in self.tricks:
      taken[t.winner] += t.points
    return taken

  def known_re_players(self):
    known = set()
    for t in self.tricks:
      for i, c in enumerate(t.cards):
        if c == cards.CLUB_QUEEN:
          known.add(t.player_of(i))
    for i, c in enumerate(self.current_trick):
      if c == cards.CLUB_QUEEN:
        known.add((self.trick_leader + i) % cards.NUM_PLAYERS)
    return known


def iter_plays(state):
  """Yields (seat, card, led_card) for every play in public history.

  `led_card` is None for the play that leads its trick.
  """
  for t in state.tricks:
    for i, c in enumerate(t.cards):
      yield t.player_of(i), c, t.cards[0] if i else None
  for i, c in enumerate(state.current_trick):
    seat = (state.trick_leader + i) % cards.NUM_PLAYERS
    yield seat, c, state.current_trick[0] if i else None


def infer_voids(state):
  """Public knowledge of exhausted follow classes, per seat.

  Returns a list of four sets of follow classes (cards.TRUMP_CLASS or a
  plain suit index): whenever a player did not follow the led class,
  everyone knows they hold no card of it.
  """
  voids = [set() for _ in range(cards.NUM_PLAYERS)]
  for seat, card, led in iter_plays(state):
    if led is not None:
      led_class = cards.card_class(led)
      if cards.card_class(card) != led_class:
        voids[seat].add(led_class)
  return voids


def cards_played_by_seat(state):
  """Number of cards each seat has played so far."""
  played = [0] * cards.NUM_PLAYERS
  for seat, _, _ in iter_plays(state):
    played[seat] += 1
  return played


def played_counts(state):
  """Copies of each card type in the public discard (played cards)."""
  counts = [0] * cards.NUM_CARD_TYPES
  for _, card, _ in iter_plays(state):
    counts[card] += 1
  return counts


def unseen_counts(state, player):
  """Card copies not visible to `player`: 2 - played - own hand."""
  played = played_counts(state)
  return [2 - played[c] - state.hands[player][c]
          for c in range(cards.NUM_CARD_TYPES)]


class InconsistentView(Exception):
  """No hidden-hand assignment satisfies the observed constraints."""


def sample_world(state, player, rng=None, max_tries=200):
  """Samples a LightState with hidden hands filled in consistently.

  The sampled world agrees with everything `player` can see: the public
  trick history, their own hand, hand sizes, remaining card counts and
  inferred voids. `re_players` in the world is derived from where the
  club queens land (past plays plus the sampled hands), so team info is
  consistent too.

  Args:
    state: a DoppelkopfState or LightState (play phase).
    player: the observing seat whose view must be respected.
    rng: random.Random instance.
    max_tries: attempts before declaring the view inconsistent.

  Returns:
    A LightState identical to `state` from `player`'s perspective.
  """
  rng = rng or random.Random()
  voids = infer_voids(state)
  played = cards_played_by_seat(state)
  hidden_seats = [s for s in range(cards.NUM_PLAYERS) if s != player]
  need = {s: cards.CARDS_PER_PLAYER - played[s] for s in hidden_seats}

  pool = []
  for c, n in enumerate(unseen_counts(state, player)):
    if n < 0:
      raise InconsistentView(f"negative unseen count for {cards.card_str(c)}")
    pool.extend([c] * n)
  if len(pool) != sum(need.values()):
    raise InconsistentView("unseen cards do not match hidden hand sizes")

  for _ in range(max_tries):
    hands = _try_assign(pool, hidden_seats, need, voids, rng)
    if hands is not None:
      world = LightState.from_state(state)
      for s in hidden_seats:
        world.hands[s] = hands[s]
      world.re_players = _re_players_of(world)
      return world
  raise InconsistentView("no consistent deal found (constraints too tight?)")


def _try_assign(pool, hidden_seats, need, voids, rng):
  """One randomized attempt at dealing `pool` under void constraints.

  Deals the most constrained cards first (fewest seats can take them),
  choosing a random eligible seat weighted by remaining capacity. Returns
  per-seat count vectors, or None if it dead-ends.
  """
  remaining = dict(need)
  hands = {s: [0] * cards.NUM_CARD_TYPES for s in hidden_seats}

  def eligible(card):
    cls = cards.card_class(card)
    return [s for s in hidden_seats
            if remaining[s] > 0 and cls not in voids[s]]

  deck = list(pool)
  rng.shuffle(deck)
  deck.sort(key=lambda c: len(eligible(c)))  # Most constrained first.
  for card in deck:
    seats = eligible(card)
    if not seats:
      return None
    weights = [remaining[s] for s in seats]
    seat = rng.choices(seats, weights)[0]
    hands[seat][card] += 1
    remaining[seat] -= 1
  return hands


def _re_players_of(state):
  """Seats holding (or having played) a club queen in a full world."""
  re_players = set()
  for seat, card, _ in iter_plays(state):
    if card == cards.CLUB_QUEEN:
      re_players.add(seat)
  for s in range(cards.NUM_PLAYERS):
    if state.hands[s][cards.CLUB_QUEEN] > 0:
      re_players.add(s)
  return re_players
