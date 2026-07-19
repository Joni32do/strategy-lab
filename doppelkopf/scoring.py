"""End-of-game scoring for the normal Doppelkopf game.

Kept free of any OpenSpiel dependency so it can be unit-tested directly
and reused by the CLI for the final score breakdown.
"""

import dataclasses

from doppelkopf import cards


@dataclasses.dataclass(frozen=True)
class Rules:
  """Toggleable special rules a rulebook lists on top of the base game.

  The defaults are the common tournament conventions:

    second_dulle: the later of the two 10-hearts (the "Dulle") beats the
      earlier one, so a Dulle can be over-trumped by the other Dulle.
      With this off, identical cards keep the first-played-wins rule and
      the first Dulle stays on top.
    karlchen: winning the very last trick with a jack of clubs earns an
      extra game point ("Karlchen"). With this off it scores nothing.
  """

  second_dulle: bool = True
  karlchen: bool = True


DEFAULT_RULES = Rules()


class Trick:
  """A completed trick: who led, the four cards in play order."""

  def __init__(self, leader, played, rules=DEFAULT_RULES):
    assert len(played) == cards.NUM_PLAYERS
    self.leader = leader
    self.cards = list(played)
    offset = cards.trick_winner_offset(self.cards,
                                       second_dulle=rules.second_dulle)
    self.winner = (leader + offset) % cards.NUM_PLAYERS
    self.winning_card = self.cards[offset]
    self.points = sum(cards.card_points(c) for c in self.cards)

  def player_of(self, index):
    """Seat of the card at position `index` in play order."""
    return (self.leader + index) % cards.NUM_PLAYERS


def compute_result(re_players, tricks, rules=DEFAULT_RULES):
  """Scores a finished game.

  Args:
    re_players: set of seats holding a club queen at the deal.
    tricks: list of 12 completed Tricks.
    rules: the Rules in force (which special points are awarded).

  Returns:
    A dict with the full breakdown:
      re_points / kontra_points: card points per team.
      re_wins: True if Re reached 121 points.
      base: list of (label, +1) game points for the winning team.
      specials: list of (label, team_sign) special points, team_sign is
        +1 when it favours Re and -1 when it favours Kontra.
      value: signed game value from Re's perspective.
      returns: per-seat utilities (zero-sum; a lone Re player gets 3x).
  """
  re_players = set(re_players)
  is_re = [p in re_players for p in range(cards.NUM_PLAYERS)]

  re_points = sum(t.points for t in tricks if is_re[t.winner])
  kontra_points = cards.TOTAL_POINTS - re_points
  re_tricks = sum(1 for t in tricks if is_re[t.winner])
  re_wins = re_points >= 121

  winner_points = re_points if re_wins else kontra_points
  loser_points = kontra_points if re_wins else re_points
  loser_tricks = len(tricks) - re_tricks if re_wins else re_tricks

  base = [("won", 1)]
  if loser_points < 90:
    base.append(("no 90", 1))
  if loser_points < 60:
    base.append(("no 60", 1))
  if loser_points < 30:
    base.append(("no 30", 1))
  if loser_tricks == 0:
    base.append(("schwarz", 1))
  if not re_wins:
    base.append(("against the queens", 1))

  specials = []
  for t in tricks:
    winner_sign = 1 if is_re[t.winner] else -1
    # Fox: an ace of diamonds captured by the other team.
    for i, c in enumerate(t.cards):
      if c == cards.DIAMOND_ACE and is_re[t.player_of(i)] != is_re[t.winner]:
        specials.append(("fox caught", winner_sign))
    # Doppelkopf: a trick worth 40 or more points.
    if t.points >= 40:
      specials.append(("doppelkopf", winner_sign))
  # Karlchen: winning the last trick with a jack of clubs.
  if rules.karlchen:
    last = tricks[-1]
    if last.winning_card == cards.CLUB_JACK:
      specials.append(("karlchen", 1 if is_re[last.winner] else -1))

  base_total = sum(v for _, v in base)
  special_total = sum(sign for _, sign in specials)
  value = (base_total if re_wins else -base_total) + special_total

  # A lone Re player (silent wedding) wins or loses triple, keeping the
  # returns zero-sum: +-3v against three opponents at -+v each.
  re_multiplier = 3 if len(re_players) == 1 else 1
  returns = [
      float(value) * re_multiplier if is_re[p] else float(-value)
      for p in range(cards.NUM_PLAYERS)
  ]

  return {
      "re_points": re_points,
      "kontra_points": kontra_points,
      "re_wins": re_wins,
      "winner_points": winner_points,
      "loser_points": loser_points,
      "base": base,
      "specials": specials,
      "value": value,
      "returns": returns,
  }
