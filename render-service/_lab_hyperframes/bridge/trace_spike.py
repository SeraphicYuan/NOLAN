"""Raster line-art -> centerline SVG paths (the spike). threshold -> skeletonize -> walk the
1px skeleton into polylines between endpoints/junctions -> RDP-simplify -> path `d` strings.
Emits {viewBox, paths} JSON for the linedraw block. Centerline (pen-like), NOT potrace outline."""
import sys, json
import cv2, numpy as np
from skimage.morphology import skeletonize

inp, out = sys.argv[1], sys.argv[2]
img = cv2.imread(inp, cv2.IMREAD_GRAYSCALE)
H, W = img.shape
binary = img < 128                      # dark strokes = foreground
skel = skeletonize(binary)
ys, xs = np.where(skel)
pts = set(zip(xs.tolist(), ys.tolist()))

def neigh(x, y):
    return [(x+dx, y+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if not (dx == 0 and dy == 0) and (x+dx, y+dy) in pts]

deg = {p: len(neigh(*p)) for p in pts}
seen = set()
def edge(a, b): return (a, b) if a <= b else (b, a)
polys = []

def walk(start):
    for nb in neigh(*start):
        if edge(start, nb) in seen:
            continue
        poly, prev, cur = [start, nb], start, nb
        seen.add(edge(prev, cur))
        while deg.get(cur, 0) == 2:
            nxt = next((n for n in neigh(*cur) if n != prev and edge(cur, n) not in seen), None)
            if nxt is None:
                break
            seen.add(edge(cur, nxt)); poly.append(nxt); prev, cur = cur, nxt
        polys.append(poly)

for p in [q for q in pts if deg[q] != 2]:   # endpoints + junctions first
    walk(p)
for p in pts:                                # then any leftover loops
    if any(edge(p, n) not in seen for n in neigh(*p)):
        walk(p)

def to_d(poly):
    arr = np.array(poly, np.int32).reshape(-1, 1, 2)
    ap = cv2.approxPolyDP(arr, 1.6, False).reshape(-1, 2)   # RDP simplify
    if len(ap) < 2:
        return None
    return "M " + " L ".join(f"{int(x)} {int(y)}" for x, y in ap)

paths = [d for d in (to_d(p) for p in polys if len(p) >= 5) if d]
json.dump({"viewBox": f"0 0 {W} {H}", "paths": paths}, open(out, "w"))
print(f"traced {len(paths)} paths from {len(pts)} skeleton px ({W}x{H})")
