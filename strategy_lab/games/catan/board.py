"""Board geometry of the base Catan map, for the ``hex`` scene part.

Catanatron numbers tiles, nodes, edges and ports by the *topology* of the
standard map, so ids do not change between games (only resources, number
tokens and port types are shuffled). The geometry is therefore computed once
from a template map: tile centers, the six corner nodes of every tile
(north, north-east, south-east, south, south-west, north-west), node
positions and the node pair of every port.

Coordinates are in a plane where one hex has corner radius :data:`SIZE`;
``WIDTH`` and ``HEIGHT`` give the bounding box after shifting to the origin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from catanatron.models.map import BASE_MAP_TEMPLATE, PORT_DIRECTION_TO_NODEREFS, CatanMap
from catanatron.models.tiles import LandTile, Port

SIZE = 10.0
_ANGLE = {"NORTH": -90, "NORTHEAST": -30, "SOUTHEAST": 30, "SOUTH": 90,
          "SOUTHWEST": 150, "NORTHWEST": 210}
_RING = ("NORTH", "NORTHEAST", "SOUTHEAST", "SOUTH", "SOUTHWEST", "NORTHWEST")
_PAD = 8.0


@dataclass(frozen=True)
class TileGeometry:
    id: int
    coord: tuple[int, int, int]
    cx: float
    cy: float
    nodes: tuple[int, ...]       # six corner node ids, north first, clockwise


@dataclass(frozen=True)
class PortGeometry:
    id: int
    nodes: tuple[int, int]
    x: float                     # label position, pushed outward from the board
    y: float


def _build():
    template = CatanMap.from_template(BASE_MAP_TEMPLATE)
    raw_nodes: dict[int, tuple[float, float]] = {}
    raw_tiles = []
    for coord, tile in template.tiles.items():
        if not isinstance(tile, LandTile):
            continue
        q, r = coord[0], coord[2]
        cx = SIZE * math.sqrt(3) * (q + r / 2.0)
        cy = SIZE * 1.5 * r
        ring = []
        for ref in _RING:
            node = {k.value: v for k, v in tile.nodes.items()}[ref]
            a = math.radians(_ANGLE[ref])
            raw_nodes[node] = (cx + SIZE * math.cos(a), cy + SIZE * math.sin(a))
            ring.append(node)
        raw_tiles.append((tile.id, coord, cx, cy, tuple(ring)))
    ox = min(x for x, _ in raw_nodes.values()) - _PAD
    oy = min(y for _, y in raw_nodes.values()) - _PAD
    nodes = {n: (round(x - ox, 2), round(y - oy, 2)) for n, (x, y) in raw_nodes.items()}
    tiles = {t[0]: TileGeometry(t[0], t[1], round(t[2] - ox, 2), round(t[3] - oy, 2), t[4])
             for t in raw_tiles}
    width = round(max(x for x, _ in nodes.values()) + _PAD, 2)
    height = round(max(y for _, y in nodes.values()) + _PAD, 2)
    mid = (width / 2, height / 2)
    edges = set()
    for t in tiles.values():
        for i in range(6):
            edges.add(tuple(sorted((t.nodes[i], t.nodes[(i + 1) % 6]))))
    ports = {}
    for tile in template.tiles.values():
        if isinstance(tile, Port):
            a_ref, b_ref = PORT_DIRECTION_TO_NODEREFS[tile.direction]
            by_ref = {k: v for k, v in tile.nodes.items()}
            pair = (by_ref[a_ref], by_ref[b_ref])
            px = (nodes[pair[0]][0] + nodes[pair[1]][0]) / 2
            py = (nodes[pair[0]][1] + nodes[pair[1]][1]) / 2
            dx, dy = px - mid[0], py - mid[1]
            norm = math.hypot(dx, dy) or 1.0
            ports[tile.id] = PortGeometry(tile.id, pair, round(px + 4.5 * dx / norm, 2),
                                          round(py + 4.5 * dy / norm, 2))
    return tiles, nodes, sorted(edges), ports, width, height


TILES, NODES, EDGES, PORTS, WIDTH, HEIGHT = _build()
TILE_OF_COORD = {t.coord: t for t in TILES.values()}
assert len(TILES) == 19 and len(NODES) == 54 and len(EDGES) == 72
