"""Card-table serializers for the OpenSpiel play sessions.

`card_view(sess)` returns the frozen `cardView` payload for the two card
games the browser renders as a table -- our Python Doppelkopf and
pyspiel's Skat -- and None for every other game (the generic text UI
still works). Everything is wrapped so a parse failure degrades to None
rather than breaking the response.

Suit convention for BOTH games in the payload: 0=Clubs, 1=Spades,
2=Hearts, 3=Diamonds. Rank strings: "7".."10","J","Q","K","A".
"""


def card_view(sess):
    """cardView dict for doppelkopf/skat sessions, else None."""
    game = sess.get("game")
    state = sess.get("state")
    if state is None:
        return None
    try:
        if game == "python_doppelkopf":
            return _doppelkopf_view(state, sess["humanSeat"])
        if game == "skat":
            return _skat_view(state, sess["humanSeat"])
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
# Doppelkopf (direct access to our Python state)
# --------------------------------------------------------------------------- #
_DK_OTHER_NAMES = ["West", "North", "East"]


def _seat_names(human, others):
    """Rotate so the human seat is "You"; others get `others` in order."""
    n = len(others) + 1
    names = [None] * n
    names[human] = "You"
    idx = 0
    for s in range(n):
        if s == human:
            continue
        names[s] = others[idx]
        idx += 1
    return names


def _doppelkopf_view(state, human):
    try:
        from doppelkopf import cards
        from doppelkopf.game import legal_cards
    except ImportError:
        return None

    terminal = state.is_terminal()
    to_act = None if terminal else int(state.current_player())
    players = cards.NUM_PLAYERS

    legal = set()
    if to_act == human:
        legal = set(legal_cards(state.hands[human], state.current_trick))

    def card_entry(c, is_legal):
        return {
            "a": int(c) if is_legal else None,
            "rank": cards.RANK_LETTERS[cards.rank_of(c)],
            "suit": int(cards.suit_of(c)),
            "trump": bool(cards.is_trump(c)),
            "points": int(cards.card_points(c)),
            "legal": bool(is_legal),
        }

    held = []
    for c in range(cards.NUM_CARD_TYPES):
        held.extend([c] * state.hands[human][c])
    hand = [card_entry(c, c in legal) for c in cards.sort_for_display(held)]

    hand_sizes = [int(sum(state.hands[p])) for p in range(players)]

    if state.current_trick:
        plays = []
        for i, c in enumerate(state.current_trick):
            seat = (state.trick_leader + i) % players
            plays.append({"seat": int(seat),
                          "rank": cards.RANK_LETTERS[cards.rank_of(c)],
                          "suit": int(cards.suit_of(c))})
        trick = {"leader": int(state.trick_leader), "plays": plays}
    else:
        trick = {"leader": -1, "plays": []}

    last_trick = None
    if state.tricks:
        t = state.tricks[-1]
        last_trick = {
            "winner": int(t.winner),
            "points": int(t.points),
            "plays": [{"seat": int(t.player_of(i)),
                       "rank": cards.RANK_LETTERS[cards.rank_of(c)],
                       "suit": int(cards.suit_of(c))}
                      for i, c in enumerate(t.cards)],
        }

    badges = [[] for _ in range(players)]
    for s in state.known_re_players():
        badges[s].append("re")
    human_tag = "re" if human in state.re_players else "kontra"
    if human_tag not in badges[human]:
        badges[human].append(human_tag)

    # Status line.
    if terminal:
        status = "Game over"
    elif to_act == human:
        if state.current_trick:
            led = state.current_trick[0]
            if cards.is_trump(led):
                status = "Your turn - follow trump"
            else:
                status = "Your turn - follow %s" % cards.SUIT_NAMES[
                    cards.suit_of(led)].lower()
        else:
            status = "Your turn - lead"
    else:
        status = "%s to play" % _seat_names(human, _DK_OTHER_NAMES)[to_act]

    result = None
    if terminal:
        res = state.result()
        result = {
            "returns": [round(float(r), 4) for r in res["returns"]],
            "re_points": int(res["re_points"]),
            "kontra_points": int(res["kontra_points"]),
            "value": int(res["value"]),
            "re_seats": sorted(int(p) for p in state.re_players),
            "specials": [[label, int(sign)] for label, sign in res["specials"]],
            "base": [[label, int(n)] for label, n in res["base"]],
        }

    return {
        "kind": "doppelkopf",
        "phase": "play",
        "players": players,
        "humanSeat": int(human),
        "toAct": to_act,
        "terminal": bool(terminal),
        "seatNames": _seat_names(human, _DK_OTHER_NAMES),
        "hand": hand,
        "handSizes": hand_sizes,
        "trick": trick,
        "lastTrick": last_trick,
        "pointsTaken": [int(x) for x in state.points_taken()],
        "badges": badges,
        "actions": [],
        "status": status,
        "result": result,
    }


# --------------------------------------------------------------------------- #
# Skat (observation-string parsing; never peek other hands)
# --------------------------------------------------------------------------- #
# Payload suit index by suit letter used in skat action names / glyphs.
_SKAT_SUIT_IDX = {"C": 0, "S": 1, "H": 2, "D": 3}
# Unicode playing-card rows: A/B/C/D = spades/hearts/diamonds/clubs.
_GLYPH_ROW_SUIT = {0: "S", 1: "H", 2: "D", 3: "C"}
_GLYPH_NIBBLE_RANK = {0x1: "A", 0x7: "7", 0x8: "8", 0x9: "9", 0xA: "10",
                      0xB: "J", 0xD: "Q", 0xE: "K"}
_SKAT_RANK_POINTS = {"A": 11, "10": 10, "K": 4, "Q": 3, "J": 2,
                     "9": 0, "8": 0, "7": 0}
# Display order within a suit, strongest first (suit games / grand).
_SKAT_RANK_ORDER = {"A": 0, "10": 1, "K": 2, "Q": 3, "9": 4, "8": 5, "7": 6}
_SKAT_NUM_CARDS = 32
_SKAT_HAND0 = 10  # cards each seat plays with.

# name (e.g. "DQ") -> action id, built lazily from action_to_string.
_SKAT_NAME_TO_ACTION = None
# (suit_letter, rank_str) -> action id.
_SKAT_CARD_TO_ACTION = None


def _skat_build_maps():
    global _SKAT_NAME_TO_ACTION, _SKAT_CARD_TO_ACTION
    if _SKAT_NAME_TO_ACTION is not None:
        return
    import pyspiel
    g = pyspiel.load_game("skat")
    s = g.new_initial_state()
    while s.is_chance_node():
        s.apply_action(s.chance_outcomes()[0][0])
    p = s.current_player()
    name_to_action = {}
    card_to_action = {}
    for a in range(_SKAT_NUM_CARDS):
        name = s.action_to_string(p, a)  # e.g. "DQ", "H7", "ST"
        name_to_action[name] = a
        suit, rank = _skat_split_name(name)
        if suit is not None:
            card_to_action[(suit, rank)] = a
    _SKAT_NAME_TO_ACTION = name_to_action
    _SKAT_CARD_TO_ACTION = card_to_action


def _skat_split_name(name):
    """Skat card action name 'DQ'/'H7'/'ST' -> (suit_letter, rank_str)."""
    if not name or name[0] not in _SKAT_SUIT_IDX:
        return None, None
    suit = name[0]
    rank = name[1:]
    if rank == "T":
        rank = "10"
    return suit, rank


def _skat_decode_glyph(ch):
    """Unicode card glyph -> (suit_letter, rank_str) or (None, None)."""
    off = ord(ch) - 0x1F0A0
    if off < 0:
        return None, None
    row, nibble = off // 16, off % 16
    suit = _GLYPH_ROW_SUIT.get(row)
    rank = _GLYPH_NIBBLE_RANK.get(nibble)
    if suit is None or rank is None:
        return None, None
    return suit, rank


def _skat_glyphs(text):
    """Decode a run of card glyphs (space-separated) to (suit,rank) list."""
    out = []
    for ch in text.strip().split():
        suit, rank = _skat_decode_glyph(ch)
        if suit is not None:
            out.append((suit, rank))
    return out


def _skat_is_trump(suit, rank, game):
    """Trump flag relative to the declared game (best effort)."""
    if game in ("diamonds", "hearts", "spades", "clubs"):
        if rank == "J":
            return True
        trump_letter = {"diamonds": "D", "hearts": "H",
                        "spades": "S", "clubs": "C"}[game]
        return suit == trump_letter
    if game == "grand":
        return rank == "J"
    return False  # null or unknown/pass


def _skat_card_dict(suit, rank):
    return {"rank": rank, "suit": _SKAT_SUIT_IDX[suit]}


def _skat_parse_obs(obs):
    """Split the observation into a field dict tolerant of odd keys."""
    fields = {"Phase": "", "Hand": "", "Skat": "", "Game": "",
              "SoloPl": "-1", "PlPos": "-1",
              "CurrTrickLeader": "-1", "CurrTrick": "",
              "PrevTrickLeader": "-1", "PrevTrick": "", "has_prev": False}
    for part in obs.split("|"):
        if part.startswith("PlPos:"):
            fields["PlPos"] = part[len("PlPos:"):]
        elif part.startswith("Phase:"):
            fields["Phase"] = part[len("Phase:"):]
        elif part.startswith("Hand:"):
            fields["Hand"] = part[len("Hand:"):]
        elif part.startswith("Skat:"):
            fields["Skat"] = part[len("Skat:"):]
        elif part.startswith("SoloPl:"):
            fields["SoloPl"] = part[len("SoloPl:"):]
        elif part.startswith("Game:"):
            fields["Game"] = part[len("Game:"):]
        elif part.startswith("CurrTrick(Leader:"):
            lead, rest = _skat_split_trick(part, "CurrTrick(Leader:")
            fields["CurrTrickLeader"], fields["CurrTrick"] = lead, rest
        elif part.startswith("PrevTrick(Leader:"):
            lead, rest = _skat_split_trick(part, "PrevTrick(Leader:")
            fields["PrevTrickLeader"], fields["PrevTrick"] = lead, rest
            fields["has_prev"] = True
    return fields


def _skat_last_trick_winner(state):
    """Winner of the last completed trick from the engine's public state
    string ("Last trick won by player N"), or None if unavailable."""
    import re
    try:
        m = re.search(r"Last trick won by player (\d+)", str(state))
    except Exception:
        return None
    if not m:
        return None
    w = int(m.group(1))
    return w if 0 <= w < 3 else None


def _skat_split_trick(part, prefix):
    """'CurrTrick(Leader:0):<glyphs>' -> ('0', '<glyphs>')."""
    body = part[len(prefix):]
    close = body.find("):")
    if close < 0:
        return "-1", ""
    return body[:close], body[close + 2:]


def _to_int(text, default=-1):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _skat_view(state, human):
    try:
        _skat_build_maps()
    except Exception:
        return None

    terminal = state.is_terminal()
    players = 3
    to_act = None
    if not terminal:
        cur = state.current_player()
        if cur >= 0:
            to_act = int(cur)

    try:
        obs = state.observation_string(human)
    except Exception:
        obs = ""
    f = _skat_parse_obs(obs)

    phase_raw = f["Phase"]
    if phase_raw.startswith("bidding"):
        phase = "bid"
    elif phase_raw.startswith("discarding"):
        phase = "discard"
    else:
        phase = "play"

    game = f["Game"]
    game_known = game not in ("", "unknown/pass")

    legal_actions = [] if terminal else list(state.legal_actions())
    legal_set = set(legal_actions)
    my_turn = (to_act == human) and not terminal

    # Hand cards, with action id when this seat may play/discard now.
    hand_cards = _skat_glyphs(f["Hand"])

    def sort_key(item):
        suit, rank = item
        trump = _skat_is_trump(suit, rank, game)
        if trump:
            # Jacks strongest (C,S,H,D order), then trump-suit A,10,K,Q,9,8,7.
            if rank == "J":
                jack_order = {"C": 0, "S": 1, "H": 2, "D": 3}[suit]
                return (0, 0, jack_order)
            return (0, 1, _SKAT_RANK_ORDER.get(rank, 9))
        return (1, _SKAT_SUIT_IDX[suit], _SKAT_RANK_ORDER.get(rank, 9))

    hand = []
    for suit, rank in sorted(hand_cards, key=sort_key):
        a = _SKAT_CARD_TO_ACTION.get((suit, rank))
        is_legal = bool(my_turn and a is not None and a in legal_set)
        hand.append({
            "a": int(a) if is_legal else None,
            "rank": rank,
            "suit": _SKAT_SUIT_IDX[suit],
            "trump": bool(_skat_is_trump(suit, rank, game) if game_known else False),
            "points": int(_SKAT_RANK_POINTS.get(rank, 0)),
            "legal": is_legal,
        })

    # Current (incomplete) trick.
    curr_leader = _to_int(f["CurrTrickLeader"])
    curr_cards = _skat_glyphs(f["CurrTrick"])
    if curr_cards and curr_leader >= 0:
        plays = []
        for i, (suit, rank) in enumerate(curr_cards):
            seat = (curr_leader + i) % players
            plays.append({"seat": int(seat), "rank": rank,
                          "suit": _SKAT_SUIT_IDX[suit]})
        trick = {"leader": int(curr_leader), "plays": plays}
    else:
        trick = {"leader": -1, "plays": []}

    # Last trick: winner led the current trick (trick-winner-leads rule).
    last_trick = None
    if f["has_prev"]:
        prev_leader = _to_int(f["PrevTrickLeader"])
        prev_cards = _skat_glyphs(f["PrevTrick"])
        if prev_cards:
            # Trick-winner-leads gives the winner as the current leader;
            # at terminal there is no current trick, so ask the engine
            # (falling back to the inference, then the previous leader).
            winner = _skat_last_trick_winner(state)
            if winner is None:
                winner = curr_leader if curr_leader >= 0 else prev_leader
            plays = []
            for i, (suit, rank) in enumerate(prev_cards):
                seat = (prev_leader + i) % players
                plays.append({"seat": int(seat), "rank": rank,
                              "suit": _SKAT_SUIT_IDX[suit]})
            points = sum(_SKAT_RANK_POINTS.get(r, 0) for _, r in prev_cards)
            last_trick = {"winner": int(winner), "points": int(points),
                          "plays": plays}

    # Hand sizes (public counts, derived without peeking hidden cards).
    hand_sizes = _skat_hand_sizes(human, phase, len(hand_cards),
                                  curr_leader, len(curr_cards), players)

    # Badges: declarer + declared game type.
    badges = [[] for _ in range(players)]
    solo = _to_int(f["SoloPl"])
    if 0 <= solo < players:
        badges[solo].append("declarer")
        if game_known:
            badges[solo].append(game)

    # Non-card actions (bids / declarations) for the human right now.
    actions = []
    if my_turn:
        for a in legal_actions:
            if a >= _SKAT_NUM_CARDS:
                actions.append({"a": int(a),
                                "s": state.action_to_string(human, a)})

    # Status line.
    seat_names = _seat_names(human, ["Left", "Right"])
    if terminal:
        status = "Game over"
    elif phase == "bid":
        status = ("Bidding - declare a game or pass" if my_turn
                  else "%s is bidding" % seat_names[to_act])
    elif phase == "discard":
        status = ("Discard 2 cards to the skat" if my_turn
                  else "%s to discard" % seat_names[to_act])
    elif my_turn:
        status = "Your turn to play"
    elif to_act is not None:
        status = "%s to play" % seat_names[to_act]
    else:
        status = "Waiting"

    result = None
    if terminal:
        result = {"returns": [round(float(r), 4) for r in state.returns()]}

    return {
        "kind": "skat",
        "phase": phase,
        "players": players,
        "humanSeat": int(human),
        "toAct": to_act,
        "terminal": bool(terminal),
        "seatNames": seat_names,
        "hand": hand,
        "handSizes": hand_sizes,
        "trick": trick,
        "lastTrick": last_trick,
        "pointsTaken": None,
        "badges": badges,
        "actions": actions,
        "status": status,
        "result": result,
    }


def _skat_hand_sizes(human, phase, human_hand_len, curr_leader, curr_plays,
                     players):
    """Best-effort public hand counts, from the human's own view only."""
    if phase != "play":
        sizes = [_SKAT_HAND0] * players
        sizes[human] = human_hand_len
        return sizes
    human_played = _skat_seat_played(human, curr_leader, curr_plays, players)
    tricks_done = _SKAT_HAND0 - human_hand_len - (1 if human_played else 0)
    if tricks_done < 0:
        tricks_done = 0
    sizes = []
    for s in range(players):
        played = _skat_seat_played(s, curr_leader, curr_plays, players)
        sizes.append(max(0, _SKAT_HAND0 - tricks_done - (1 if played else 0)))
    return sizes


def _skat_seat_played(seat, leader, num_plays, players):
    """Has `seat` already played in the current trick of `num_plays` cards?"""
    if leader < 0 or num_plays <= 0:
        return False
    played_seats = {(leader + i) % players for i in range(num_plays)}
    return seat in played_seats
