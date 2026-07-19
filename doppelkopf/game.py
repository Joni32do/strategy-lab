"""Doppelkopf (normal game) implemented as an OpenSpiel Python game.

Four players, 48 cards (a doubled 9-to-ace deck). The two holders of the
club queens form the hidden Re team against Kontra. Standard trick play
with the normal-game trump order; scoring includes no-90/60/30, schwarz,
"against the queens", fox, doppelkopf and karlchen special points. A
player dealt both club queens plays a silent wedding: alone as Re for a
tripled score. Reservations, solos and Re/Kontra announcements are not
modelled.

Registered under the short name "python_doppelkopf".
"""

import numpy as np

import pyspiel

from doppelkopf import cards
from doppelkopf import scoring

_GAME_TYPE = pyspiel.GameType(
    short_name="python_doppelkopf",
    long_name="Python Doppelkopf (normal game)",
    dynamics=pyspiel.GameType.Dynamics.SEQUENTIAL,
    chance_mode=pyspiel.GameType.ChanceMode.EXPLICIT_STOCHASTIC,
    information=pyspiel.GameType.Information.IMPERFECT_INFORMATION,
    utility=pyspiel.GameType.Utility.ZERO_SUM,
    reward_model=pyspiel.GameType.RewardModel.TERMINAL,
    max_num_players=cards.NUM_PLAYERS,
    min_num_players=cards.NUM_PLAYERS,
    provides_information_state_string=True,
    provides_information_state_tensor=False,
    provides_observation_string=True,
    provides_observation_tensor=True,
    parameter_specification={
        # Optional special rules (see scoring.Rules). Defaults match the
        # common tournament conventions.
        "second_dulle": True,
        "karlchen": True,
    },
)

# Bound on |game value|: 6 base points, up to 9 net special points, and a
# factor 3 for a silent wedding.
_MAX_UTILITY = 45.0

_GAME_INFO = pyspiel.GameInfo(
    num_distinct_actions=cards.NUM_CARD_TYPES,
    max_chance_outcomes=cards.NUM_CARD_TYPES,
    num_players=cards.NUM_PLAYERS,
    min_utility=-_MAX_UTILITY,
    max_utility=_MAX_UTILITY,
    utility_sum=0.0,
    max_game_length=cards.NUM_CARDS + cards.NUM_CARDS,  # deal + play
)


class DoppelkopfGame(pyspiel.Game):
  """A Python version of Doppelkopf (normal game only)."""

  def __init__(self, params=None):
    super().__init__(_GAME_TYPE, _GAME_INFO, params or dict())
    p = self.get_parameters()
    self.rules = scoring.Rules(
        second_dulle=bool(p.get("second_dulle", True)),
        karlchen=bool(p.get("karlchen", True)))

  def new_initial_state(self):
    return DoppelkopfState(self)

  def make_py_observer(self, iig_obs_type=None, params=None):
    return DoppelkopfObserver(
        iig_obs_type or pyspiel.IIGObservationType(perfect_recall=False),
        params)


class DoppelkopfState(pyspiel.State):
  """State of a Doppelkopf game."""

  def __init__(self, game):
    super().__init__(game)
    self.rules = game.rules
    # Remaining physical copies of each card type during the deal.
    self._deck_counts = [2] * cards.NUM_CARD_TYPES
    self._num_dealt = 0
    # Per-player counts of each card type.
    self.hands = [[0] * cards.NUM_CARD_TYPES for _ in range(cards.NUM_PLAYERS)]
    self.tricks = []  # Completed scoring.Trick objects.
    self.trick_leader = 0
    self.current_trick = []  # Card types in play order.
    self.re_players = set()  # Seats dealt a club queen.

  # --- OpenSpiel API ---

  def current_player(self):
    if self.is_terminal():
      return pyspiel.PlayerId.TERMINAL
    if self._num_dealt < cards.NUM_CARDS:
      return pyspiel.PlayerId.CHANCE
    return (self.trick_leader + len(self.current_trick)) % cards.NUM_PLAYERS

  def is_terminal(self):
    return len(self.tricks) == cards.NUM_TRICKS

  def chance_outcomes(self):
    assert self.is_chance_node()
    remaining = cards.NUM_CARDS - self._num_dealt
    return [(c, n / remaining)
            for c, n in enumerate(self._deck_counts) if n > 0]

  def _legal_actions(self, player):
    return legal_cards(self.hands[player], self.current_trick)

  def _apply_action(self, action):
    if self.is_chance_node():
      seat = self._num_dealt // cards.CARDS_PER_PLAYER
      self._deck_counts[action] -= 1
      self.hands[seat][action] += 1
      self._num_dealt += 1
      if action == cards.CLUB_QUEEN:
        self.re_players.add(seat)
      return

    player = self.current_player()
    assert self.hands[player][action] > 0
    self.hands[player][action] -= 1
    self.current_trick.append(action)
    if len(self.current_trick) == cards.NUM_PLAYERS:
      trick = scoring.Trick(self.trick_leader, self.current_trick, self.rules)
      self.tricks.append(trick)
      self.trick_leader = trick.winner
      self.current_trick = []

  def returns(self):
    if not self.is_terminal():
      return [0.0] * cards.NUM_PLAYERS
    return self.result()["returns"]

  def _action_to_string(self, player, action):
    name = cards.card_str(action)
    if player == pyspiel.PlayerId.CHANCE:
      return f"Deal {name}"
    return f"Play {name}"

  def __str__(self):
    hands = [hand_str(h) for h in self.hands]
    played = " | ".join(
        " ".join(cards.card_str(c) for c in t.cards) for t in self.tricks)
    current = " ".join(cards.card_str(c) for c in self.current_trick)
    return (f"hands:{hands} re:{sorted(self.re_players)} "
            f"tricks:[{played}] current:[{current}]")

  # --- Helpers shared with the observer, bots and the CLI ---

  def result(self):
    """Full scoring breakdown; only valid on a terminal state."""
    assert self.is_terminal()
    return scoring.compute_result(self.re_players, self.tricks, self.rules)

  def points_taken(self):
    """Card points captured so far, per seat (public information)."""
    taken = [0] * cards.NUM_PLAYERS
    for t in self.tricks:
      taken[t.winner] += t.points
    return taken

  def known_re_players(self):
    """Seats publicly known to be Re (they played a club queen)."""
    known = set()
    for t in self.tricks:
      for i, c in enumerate(t.cards):
        if c == cards.CLUB_QUEEN:
          known.add(t.player_of(i))
    for i, c in enumerate(self.current_trick):
      if c == cards.CLUB_QUEEN:
        known.add((self.trick_leader + i) % cards.NUM_PLAYERS)
    return known


def legal_cards(hand, current_trick):
  """Distinct playable card types given a hand (counts) and the trick."""
  held = [c for c in range(cards.NUM_CARD_TYPES) if hand[c] > 0]
  if current_trick:
    led = cards.card_class(current_trick[0])
    following = [c for c in held if cards.card_class(c) == led]
    if following:
      return following
  return held


def hand_str(hand):
  """ASCII rendering of a hand given as per-type counts."""
  listed = []
  for c in range(cards.NUM_CARD_TYPES):
    listed.extend([c] * hand[c])
  return " ".join(cards.card_str(c) for c in cards.sort_for_display(listed))


class DoppelkopfObserver:
  """Observer, conforming to the PyObserver interface."""

  def __init__(self, iig_obs_type, params):
    if params:
      raise ValueError(f"Observation parameters not supported; got {params}")
    self._iig_obs_type = iig_obs_type

    pieces = [("player", cards.NUM_PLAYERS, (cards.NUM_PLAYERS,))]
    if iig_obs_type.private_info == pyspiel.PrivateInfoType.SINGLE_PLAYER:
      pieces.append(("hand", cards.NUM_CARD_TYPES, (cards.NUM_CARD_TYPES,)))
    if iig_obs_type.public_info:
      if iig_obs_type.perfect_recall:
        # Every play so far: seat one-hot (4) + card one-hot (24).
        pieces.append(("history", cards.NUM_CARDS * 28, (cards.NUM_CARDS, 28)))
      else:
        pieces.append(("current_trick", cards.NUM_PLAYERS *
                       cards.NUM_CARD_TYPES,
                       (cards.NUM_PLAYERS, cards.NUM_CARD_TYPES)))
        pieces.append(("leader", cards.NUM_PLAYERS, (cards.NUM_PLAYERS,)))
        pieces.append(("points_taken", cards.NUM_PLAYERS,
                       (cards.NUM_PLAYERS,)))

    total_size = sum(size for _, size, _ in pieces)
    self.tensor = np.zeros(total_size, np.float32)
    self.dict = {}
    index = 0
    for name, size, shape in pieces:
      self.dict[name] = self.tensor[index:index + size].reshape(shape)
      index += size

  def set_from(self, state, player):
    self.tensor.fill(0)
    if "player" in self.dict:
      self.dict["player"][player] = 1
    if "hand" in self.dict:
      for c in range(cards.NUM_CARD_TYPES):
        self.dict["hand"][c] = state.hands[player][c]
    if "history" in self.dict:
      row = 0
      for trick in state.tricks:
        for i, c in enumerate(trick.cards):
          self.dict["history"][row][trick.player_of(i)] = 1
          self.dict["history"][row][cards.NUM_PLAYERS + c] = 1
          row += 1
      for i, c in enumerate(state.current_trick):
        seat = (state.trick_leader + i) % cards.NUM_PLAYERS
        self.dict["history"][row][seat] = 1
        self.dict["history"][row][cards.NUM_PLAYERS + c] = 1
        row += 1
    if "current_trick" in self.dict:
      for i, c in enumerate(state.current_trick):
        seat = (state.trick_leader + i) % cards.NUM_PLAYERS
        self.dict["current_trick"][seat][c] = 1
    if "leader" in self.dict:
      self.dict["leader"][state.trick_leader] = 1
    if "points_taken" in self.dict:
      for seat, pts in enumerate(state.points_taken()):
        self.dict["points_taken"][seat] = pts / cards.TOTAL_POINTS

  def string_from(self, state, player):
    parts = [f"p{player}"]
    if self._iig_obs_type.private_info == pyspiel.PrivateInfoType.SINGLE_PLAYER:
      parts.append(f"hand:[{hand_str(state.hands[player])}]")
    if self._iig_obs_type.public_info:
      current = " ".join(cards.card_str(c) for c in state.current_trick)
      if self._iig_obs_type.perfect_recall:
        played = " | ".join(
            f"{t.leader}:" + " ".join(cards.card_str(c) for c in t.cards)
            for t in state.tricks)
        parts.append(f"tricks:[{played}] current:{state.trick_leader}:"
                     f"[{current}]")
      else:
        pts = ",".join(str(p) for p in state.points_taken())
        parts.append(f"current:{state.trick_leader}:[{current}] pts:[{pts}]")
    return " ".join(parts)


pyspiel.register_game(_GAME_TYPE, DoppelkopfGame)
