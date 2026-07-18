"""Interactive terminal Doppelkopf: you against three heuristic bots.

Run from the repository root:

    python -m doppelkopf.cli [--seed N] [--auto] [--fast]
"""

import argparse
import random
import sys
import time

import pyspiel

import doppelkopf.game  # noqa: F401  (registers python_doppelkopf)
from doppelkopf import cards
from doppelkopf.bots import HeuristicBot
from doppelkopf.game import legal_cards

# --- ANSI styling ---------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
WHITE = "\033[97m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
GREEN = "\033[92m"
GRAY = "\033[90m"

SUIT_SYMBOLS = ["♣", "♠", "♥", "♦"]  # clubs spades hearts diamonds
SUIT_COLORS = [WHITE, WHITE, RED, RED]

PLAYER_NAMES = ["You", "West", "North", "East"]


def verb(seat, verb_stem):
  """Conjugates for the seat: 'You play' but 'West plays'."""
  return verb_stem if PLAYER_NAMES[seat] == "You" else verb_stem + "s"


def card_face(card):
  """Colored unicode face of a card, e.g. a red '10<heart>'."""
  color = SUIT_COLORS[cards.suit_of(card)]
  face = cards.RANK_LETTERS[cards.rank_of(card)] + SUIT_SYMBOLS[cards.suit_of(card)]
  return f"{BOLD}{color}{face}{RESET}"


def card_tag(card):
  """A bracketed card; trumps get yellow brackets, plain cards gray."""
  bracket = YELLOW if cards.is_trump(card) else GRAY
  return f"{bracket}[{RESET}{card_face(card)}{bracket}]{RESET}"


def rule(char="─", width=62, color=GRAY):
  return f"{color}{char * width}{RESET}"


# --- Rendering ------------------------------------------------------------


def hand_cards_sorted(hand):
  listed = []
  for c in range(cards.NUM_CARD_TYPES):
    listed.extend([c] * hand[c])
  return cards.sort_for_display(listed)


def render_hand(hand, legal=None):
  """Numbered hand line; if `legal` is given, illegal cards are dimmed."""
  cells = []
  for i, c in enumerate(hand_cards_sorted(hand), start=1):
    tag = card_tag(c)
    if legal is not None and c not in legal:
      tag = f"{DIM}[{cards.RANK_LETTERS[cards.rank_of(c)]}{SUIT_SYMBOLS[cards.suit_of(c)]}]{RESET}"
    cells.append(f"{GRAY}{i:>2}{RESET}{tag}")
  return "  ".join(cells)


def render_trick(state):
  parts = []
  for i, c in enumerate(state.current_trick):
    seat = (state.trick_leader + i) % cards.NUM_PLAYERS
    parts.append(f"{PLAYER_NAMES[seat]} {card_tag(c)}")
  if not parts:
    return f"{DIM}(you lead the trick){RESET}"
  pts = sum(cards.card_points(c) for c in state.current_trick)
  return "   ".join(parts) + f"   {DIM}({pts} pts on the table){RESET}"


def show_scoreboard(state):
  taken = state.points_taken()
  cells = []
  for seat in range(cards.NUM_PLAYERS):
    known = seat in state.known_re_players()
    label = f"{PLAYER_NAMES[seat]}{CYAN}*{RESET}" if known else PLAYER_NAMES[seat]
    cells.append(f"{label} {BOLD}{taken[seat]:>3}{RESET}")
  print(f"  {DIM}points taken:{RESET}  " + "   ".join(cells)
        + f"   {DIM}({CYAN}*{RESET}{DIM} = played a club queen){RESET}")


def announce(text, delay):
  print(text)
  if delay:
    time.sleep(delay)


# --- Human input ----------------------------------------------------------


def human_choice(state, seat):
  hand = state.hands[seat]
  legal = legal_cards(hand, state.current_trick)
  ordered = hand_cards_sorted(hand)
  print(f"\n  Your hand:  {render_hand(hand, legal)}")
  while True:
    try:
      raw = input(f"  {BOLD}Play which card?{RESET} [1-{len(ordered)}, q quits] ")
    except (EOFError, KeyboardInterrupt):
      print("\nBye!")
      sys.exit(0)
    raw = raw.strip().lower()
    if raw == "q":
      print("Bye!")
      sys.exit(0)
    if raw.isdigit() and 1 <= int(raw) <= len(ordered):
      card = ordered[int(raw) - 1]
      if card in legal:
        return card
      print(f"  {RED}You must follow suit -- {card_face(card)}{RED} is not "
            f"playable here.{RESET}")
    else:
      print(f"  {RED}Please enter a number between 1 and {len(ordered)}.{RESET}")


# --- Endgame report -------------------------------------------------------


def team_names(seats):
  return ", ".join(PLAYER_NAMES[s] for s in sorted(seats))


def show_result(state):
  res = state.result()
  re_seats = set(state.re_players)
  kontra_seats = set(range(cards.NUM_PLAYERS)) - re_seats

  print()
  print(rule("═", color=YELLOW))
  print(f"  {BOLD}{YELLOW}Final reckoning{RESET}")
  print(rule("═", color=YELLOW))
  silent = " (silent wedding!)" if len(re_seats) == 1 else ""
  print(f"  Re     ({team_names(re_seats)}){silent}: "
        f"{BOLD}{res['re_points']}{RESET} card points")
  print(f"  Kontra ({team_names(kontra_seats)}): "
        f"{BOLD}{res['kontra_points']}{RESET} card points")
  winner = "Re" if res["re_wins"] else "Kontra"
  print(f"\n  {GREEN}{BOLD}{winner} wins!{RESET}")

  print(f"\n  {DIM}Game points{RESET}")
  for label, v in res["base"]:
    print(f"    {winner:<6} +{v}  {label}")
  for label, sign in res["specials"]:
    team = "Re" if sign > 0 else "Kontra"
    print(f"    {team:<6} +1  {label}")
  print(f"  {DIM}Value (from Re's side):{RESET} {BOLD}{res['value']:+d}{RESET}")

  print(f"\n  {BOLD}Score{RESET}")
  for seat in range(cards.NUM_PLAYERS):
    r = res["returns"][seat]
    color = GREEN if r > 0 else RED if r < 0 else GRAY
    print(f"    {PLAYER_NAMES[seat]:<6} {color}{r:+.0f}{RESET}")
  print(rule("═", color=YELLOW))


# --- Game loop ------------------------------------------------------------


def deal(state, rng):
  while state.is_chance_node():
    actions, probs = zip(*state.chance_outcomes())
    state.apply_action(rng.choices(actions, probs)[0])


def play(seed=None, auto=False, delay=0.6):
  if auto:
    PLAYER_NAMES[0] = "South"
  rng = random.Random(seed)
  game = pyspiel.load_game("python_doppelkopf")
  state = game.new_initial_state()
  deal(state, rng)

  bots = {p: HeuristicBot(p, random.Random(rng.random()))
          for p in range(cards.NUM_PLAYERS)}
  human = None if auto else 0

  print()
  print(rule())
  print(f"  {BOLD}DOPPELKOPF{RESET}  {DIM}normal game -- 48 cards, hidden "
        f"teams, 121 points to win{RESET}")
  print(rule())
  if human is not None:
    if human in state.re_players:
      mate = "" if len(state.re_players) == 1 else " Your partner also holds one."
      print(f"  You hold a {card_face(cards.CLUB_QUEEN)}: "
            f"you play for {BOLD}Re{RESET}.{mate}")
      if len(state.re_players) == 1:
        print(f"  {YELLOW}Both club queens! You play a silent wedding -- "
              f"alone against all three.{RESET}")
    else:
      print(f"  No club queen for you: you play for {BOLD}Kontra{RESET}. "
            f"{DIM}Who your partners are will emerge...{RESET}")

  while not state.is_terminal():
    trick_no = len(state.tricks) + 1
    print(f"\n{rule()}")
    leader = state.trick_leader
    print(f"  {BOLD}Trick {trick_no}/12{RESET}   "
          f"{DIM}{PLAYER_NAMES[leader]} {verb(leader, 'lead')}{RESET}")
    if state.tricks:
      show_scoreboard(state)

    while len(state.tricks) < trick_no:
      seat = state.current_player()
      if seat == human:
        print(f"\n  On the table:  {render_trick(state)}")
        card = human_choice(state, seat)
        announce(f"  {BOLD}You{RESET} play {card_tag(card)}", 0)
      else:
        card = bots[seat].step(state)
        announce(f"  {PLAYER_NAMES[seat]} {verb(seat, 'play')} "
                 f"{card_tag(card)}", delay)
      state.apply_action(card)
      if not state.current_trick:  # The trick just completed.
        trick = state.tricks[-1]
        who = PLAYER_NAMES[trick.winner]
        take = verb(trick.winner, "take")
        announce(f"\n  {GREEN}>> {who} {take} the trick with "
                 f"{card_tag(trick.winning_card)}{GREEN} "
                 f"(+{trick.points} points){RESET}", delay)

  show_result(state)


def main():
  parser = argparse.ArgumentParser(description="Play Doppelkopf in the terminal.")
  parser.add_argument("--seed", type=int, default=None, help="deal seed")
  parser.add_argument("--auto", action="store_true",
                      help="watch four bots play instead of joining in")
  parser.add_argument("--fast", action="store_true", help="no dramatic pauses")
  args = parser.parse_args()
  play(seed=args.seed, auto=args.auto, delay=0.0 if args.fast else 0.6)


if __name__ == "__main__":
  main()
