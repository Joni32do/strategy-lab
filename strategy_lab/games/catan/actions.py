"""Stable string names for catanatron actions.

Catanatron's playable actions are namedtuples with enums inside. The lab
needs actions that survive a JSON round trip and mean the same thing in every
replay, so each action gets a short string:

=====================  ==========================================
``ROLL``               roll the dice
``END_TURN``           end the turn
``BUY_DEV``            buy a development card
``SETTLEMENT:12``      build a settlement on node 12
``CITY:12``            upgrade the settlement on node 12
``ROAD:12-13``         build a road on the edge between two nodes
``ROBBER:0,0,0:BLUE``  move the robber to the tile at a cube coordinate,
                       steal from BLUE (``-`` if nobody)
``DISCARD:WOOD``       discard one card (after a 7)
``KNIGHT``             play a knight
``ROAD_BUILDING``      play road building
``MONOPOLY:ORE``       play monopoly on a resource
``YOP:WOOD+BRICK``     play year of plenty (one or two resources)
``BANK:WOOD*4>ORE``    trade with the bank (4:1, 3:1 or 2:1)
``OFFER:1,0,0,0,0>0,1,0,0,0``  offer cards (WOOD BRICK SHEEP WHEAT ORE) for cards
``ACCEPT`` ``REJECT``  answer a trade offer
``CONFIRM:BLUE``       close the deal with BLUE
``CANCEL``             call the offer off
=====================  ==========================================

The order of :func:`sort_key` is the deterministic order of the action list.
"""

from __future__ import annotations

from catanatron.models.enums import RESOURCES, Action, ActionType, ActionType as AT
from catanatron.models.player import Color

TYPE_ORDER = (
    AT.ROLL, AT.PLAY_KNIGHT_CARD, AT.PLAY_ROAD_BUILDING, AT.PLAY_MONOPOLY,
    AT.PLAY_YEAR_OF_PLENTY, AT.BUILD_CITY, AT.BUILD_SETTLEMENT, AT.BUILD_ROAD,
    AT.BUY_DEVELOPMENT_CARD, AT.MARITIME_TRADE, AT.OFFER_TRADE, AT.ACCEPT_TRADE,
    AT.REJECT_TRADE, AT.CONFIRM_TRADE, AT.CANCEL_TRADE, AT.MOVE_ROBBER,
    AT.DISCARD_RESOURCE, AT.END_TURN)
_RANK = {t: i for i, t in enumerate(TYPE_ORDER)}


def encode(action: Action) -> str:
    """The stable string of a catanatron :class:`Action`."""
    t, v = action.action_type, action.value
    if t == AT.ROLL:
        return "ROLL"
    if t == AT.END_TURN:
        return "END_TURN"
    if t == AT.BUY_DEVELOPMENT_CARD:
        return "BUY_DEV"
    if t == AT.BUILD_SETTLEMENT:
        return f"SETTLEMENT:{v}"
    if t == AT.BUILD_CITY:
        return f"CITY:{v}"
    if t == AT.BUILD_ROAD:
        a, b = sorted(v)
        return f"ROAD:{a}-{b}"
    if t == AT.MOVE_ROBBER:
        coord, victim = v
        return f"ROBBER:{','.join(map(str, coord))}:{victim.value if victim else '-'}"
    if t == AT.DISCARD_RESOURCE:
        return f"DISCARD:{v}"
    if t == AT.PLAY_KNIGHT_CARD:
        return "KNIGHT"
    if t == AT.PLAY_ROAD_BUILDING:
        return "ROAD_BUILDING"
    if t == AT.PLAY_MONOPOLY:
        return f"MONOPOLY:{v}"
    if t == AT.PLAY_YEAR_OF_PLENTY:
        return "YOP:" + "+".join(v)
    if t == AT.MARITIME_TRADE:
        gives = [r for r in v[:-1] if r is not None]
        return f"BANK:{gives[0]}*{len(gives)}>{v[-1]}"
    if t == AT.OFFER_TRADE:
        return f"OFFER:{','.join(map(str, v[:5]))}>{','.join(map(str, v[5:10]))}"
    if t == AT.ACCEPT_TRADE:
        return "ACCEPT"
    if t == AT.REJECT_TRADE:
        return "REJECT"
    if t == AT.CONFIRM_TRADE:
        return f"CONFIRM:{v[10].value}"
    if t == AT.CANCEL_TRADE:
        return "CANCEL"
    raise ValueError(f"unknown action {action}")


def sort_key(action: Action) -> tuple:
    return (_RANK[action.action_type], encode(action))


def offer_action(color: Color, give: tuple[int, ...], get: tuple[int, ...]) -> Action:
    return Action(color, ActionType.OFFER_TRADE, (*give, *get))


def kind(code: str) -> str:
    """The leading word of an action string (``"ROAD"`` for ``"ROAD:3-4"``)."""
    return code.split(":", 1)[0]


def cards_text(freq) -> str:
    """``[1, 0, 2, 0, 0]`` -> ``"1 wood, 2 sheep"`` (``"nothing"`` if empty)."""
    parts = [f"{n} {RESOURCES[i].lower()}" for i, n in enumerate(freq) if n]
    return ", ".join(parts) if parts else "nothing"
