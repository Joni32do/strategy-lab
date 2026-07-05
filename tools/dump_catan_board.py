"""Regenerate js/games/catan-board.js from the catanatron repo.

Usage (from strategy-lab/):
    python3 -m venv /tmp/catvenv && /tmp/catvenv/bin/pip install networkx
    /tmp/catvenv/bin/python tools/dump_catan_board.py > js/games/catan-board.js

Extracts the base-board geometry (tile centers, 54 node positions, per-tile
node rings in N,NE,SE,S,SW,NW order, port nodes) from catanatron's map model.
Resources and number tokens are shuffled per game in JS, so only the static
graph is dumped here.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'catanatron', 'catanatron'))
from catanatron.models.map import CatanMap, BASE_MAP_TEMPLATE  # noqa: E402

m = CatanMap.from_template(BASE_MAP_TEMPLATE)
S = 10.0
ANG = {'NORTH': -90, 'NORTHEAST': -30, 'SOUTHEAST': 30, 'SOUTH': 90, 'SOUTHWEST': 150, 'NORTHWEST': 210}
ORDER = ['NORTH', 'NORTHEAST', 'SOUTHEAST', 'SOUTH', 'SOUTHWEST', 'NORTHWEST']

tiles = []
nodepos = {}
for coord, t in m.land_tiles.items():
    x, y, z = coord
    q, r = x, z
    cx = S * math.sqrt(3) * (q + r / 2.0)
    cy = S * 1.5 * r
    byref = {k.value: v for k, v in t.nodes.items()}
    nodes = []
    for ref in ORDER:
        nid = byref[ref]
        a = math.radians(ANG[ref])
        px, py = cx + S * math.cos(a), cy + S * math.sin(a)
        if nid in nodepos:
            ox, oy = nodepos[nid]
            assert abs(ox - px) < 0.01 and abs(oy - py) < 0.01, nid
        nodepos[nid] = (px, py)
        nodes.append(nid)
    tiles.append({'cx': cx, 'cy': cy, 'nodes': nodes})

assert len(tiles) == 19 and len(nodepos) == 54 and sorted(nodepos) == list(range(54))
edges = set()
for t in tiles:
    ns = t['nodes']
    for i in range(6):
        edges.add(tuple(sorted((ns[i], ns[(i + 1) % 6]))))
assert len(edges) == 72, len(edges)

xs = [p[0] for p in nodepos.values()]
ys = [p[1] for p in nodepos.values()]
mx, my = min(xs) - 6, min(ys) - 6
W = round(max(xs) - mx + 6, 1)
H = round(max(ys) - my + 6, 1)

ports = {}
for res, nodes in m.port_nodes.items():
    for n in nodes:
        ports[n] = res if res else 'ANY'

out = {
    'W': W, 'H': H, 'size': S,
    'tiles': [{'cx': round(t['cx'] - mx, 1), 'cy': round(t['cy'] - my, 1), 'nodes': t['nodes']} for t in tiles],
    'nodes': [[round(nodepos[i][0] - mx, 1), round(nodepos[i][1] - my, 1)] for i in range(54)],
    'ports': {str(k): v for k, v in sorted(ports.items())},
}
print('/* Generated from the catanatron repo (models/map.py, BASE_MAP_TEMPLATE):')
print(' * 19-hex base board geometry — tile centers, the 54 node positions,')
print(' * per-tile node rings (N,NE,SE,S,SW,NW) and port nodes.')
print(' * Regenerate with tools/dump_catan_board.py. */')
print('window.CATAN_BOARD = ' + json.dumps(out, separators=(',', ':')) + ';')
