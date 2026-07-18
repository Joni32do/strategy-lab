"""Card definitions and rules helpers for Doppelkopf.

Doppelkopf is played with a doubled 24-card deck (48 cards total):
9, 10, J, Q, K, A in clubs, spades, hearts and diamonds -- each twice.

A card *type* is encoded as an int in [0, 24): card = suit * 6 + rank.
The physical deck holds two copies of every card type.

In the normal game the trumps are (from weakest to strongest):
  9D KD 10D AD  JD JH JS JC  QD QH QS QC  10H (the "Dulle")
All other cards are plain-suit cards ranked A > 10 > K > 9.
"""

# Suits.
CLUBS, SPADES, HEARTS, DIAMONDS = 0, 1, 2, 3
SUIT_LETTERS = ["C", "S", "H", "D"]
SUIT_NAMES = ["Clubs", "Spades", "Hearts", "Diamonds"]

# Ranks.
NINE, TEN, JACK, QUEEN, KING, ACE = 0, 1, 2, 3, 4, 5
RANK_LETTERS = ["9", "10", "J", "Q", "K", "A"]

NUM_CARD_TYPES = 24
NUM_CARDS = 48  # Two copies of each type.
NUM_PLAYERS = 4
NUM_TRICKS = 12
CARDS_PER_PLAYER = 12
TOTAL_POINTS = 240

# Card point values by rank (9, 10, J, Q, K, A).
RANK_POINTS = [0, 10, 2, 3, 4, 11]


def make_card(suit, rank):
  return suit * 6 + rank


def suit_of(card):
  return card // 6


def rank_of(card):
  return card % 6


def card_points(card):
  return RANK_POINTS[rank_of(card)]


def card_str(card):
  """ASCII name of a card type, e.g. 'QC' or '10H'."""
  return RANK_LETTERS[rank_of(card)] + SUIT_LETTERS[suit_of(card)]


DULLE = make_card(HEARTS, TEN)
CLUB_QUEEN = make_card(CLUBS, QUEEN)
CLUB_JACK = make_card(CLUBS, JACK)
DIAMOND_ACE = make_card(DIAMONDS, ACE)  # The "Fuchs" (fox).

# Trump order for the normal game, weakest first.
TRUMP_ORDER = (
    [make_card(DIAMONDS, r) for r in (NINE, KING, TEN, ACE)]
    + [make_card(s, JACK) for s in (DIAMONDS, HEARTS, SPADES, CLUBS)]
    + [make_card(s, QUEEN) for s in (DIAMONDS, HEARTS, SPADES, CLUBS)]
    + [DULLE]
)
_TRUMP_STRENGTH = {c: i for i, c in enumerate(TRUMP_ORDER)}

# Suit "class" a card belongs to for the follow-suit rule.
TRUMP_CLASS = "T"


def is_trump(card):
  return card in _TRUMP_STRENGTH


def trump_strength(card):
  """Strength among trumps (higher wins), or None for plain cards."""
  return _TRUMP_STRENGTH.get(card)


def card_class(card):
  """Follow-suit class: TRUMP_CLASS or the plain suit index."""
  return TRUMP_CLASS if is_trump(card) else suit_of(card)


def beats(challenger, incumbent):
  """True if `challenger` beats the currently winning `incumbent` card.

  The incumbent was played earlier in the trick, so equal cards do not
  beat it (first-played wins between identical cards). A plain-suit
  challenger can only win if it matches the incumbent's suit; since the
  incumbent is always either a trump or of the led suit, this enforces
  the led-suit rule.
  """
  ts_c, ts_i = trump_strength(challenger), trump_strength(incumbent)
  if ts_c is not None and ts_i is not None:
    return ts_c > ts_i
  if ts_c is not None:
    return True
  if ts_i is not None:
    return False
  if suit_of(challenger) != suit_of(incumbent):
    return False
  # Plain cards of one suit: A > 10 > K > 9, which point values happen
  # to order strictly (11 > 10 > 4 > 0). J/Q never appear here.
  return card_points(challenger) > card_points(incumbent)


def trick_winner_offset(cards):
  """Index (0-3, play order) of the winning card in a complete trick."""
  best = 0
  for i in range(1, len(cards)):
    if beats(cards[i], cards[best]):
      best = i
  return best


def sort_for_display(cards):
  """Sorts card types: trumps strongest-first, then C, S, H high-to-low."""

  def key(card):
    ts = trump_strength(card)
    if ts is not None:
      return (0, -ts)
    return (1 + suit_of(card), -card_points(card))

  return sorted(cards, key=key)
