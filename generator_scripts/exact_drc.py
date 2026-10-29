"""Exact (vector) clearance check: tracks/vias vs tracks/vias/pads of other nets on the same layer.
Pads are treated as rectangles (or circles), which is conservative for rounded pads."""
import sys, math, itertools
from check import load_items, clearance_of, pad_layers, LAYERS
from geom import all_pads

def seg_seg(a, b, c, d):
    def ps(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)
    def inter(a, b, c, d):
        def o(p, q, r): return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0
    if inter(a, b, c, d): return 0.0
    return min(ps(a, c, d), ps(b, c, d), ps(c, a, b), ps(d, a, b))

def shapes():
    tracks, vias = load_items(sys.argv[1] if len(sys.argv) > 1 else 'out/routes.json')
    out = []   # (layer, net, kind, geom, radius, routed)
    for t in tracks:
        out.append((t['layer'], t['net'], 'seg', ((t['x1'], t['y1']), (t['x2'], t['y2'])), t['w'] / 2, True))
    for v in vias:
        for L in LAYERS:
            out.append((L, v['net'], 'seg', ((v['x'], v['y']), (v['x'], v['y'])), v['s'] / 2, True))
    for p in all_pads():
        if p['type'] == 'np_thru_hole': continue
        for L in pad_layers(p):
            if p['shape'] == 'circle':
                out.append((L, p['net'] or f"~{p['ref']}{p['num']}", 'seg', ((p['x'], p['y']), (p['x'], p['y'])), p['w'] / 2, False))
            elif p['shape'] == 'oval':
                r = min(p['w'], p['h']) / 2
                if p['w'] >= p['h']: a, b = (p['x'] - p['w'] / 2 + r, p['y']), (p['x'] + p['w'] / 2 - r, p['y'])
                else: a, b = (p['x'], p['y'] - p['h'] / 2 + r), (p['x'], p['y'] + p['h'] / 2 - r)
                out.append((L, p['net'] or f"~{p['ref']}{p['num']}", 'seg', (a, b), r, False))
            else:
                x0, y0, x1, y1 = p['x'] - p['w'] / 2, p['y'] - p['h'] / 2, p['x'] + p['w'] / 2, p['y'] + p['h'] / 2
                out.append((L, p['net'] or f"~{p['ref']}{p['num']}", 'rect', (x0, y0, x1, y1), 0, False))
    return out

def dist(a, b):
    ka, ga, ra = a[2], a[3], a[4]; kb, gb, rb = b[2], b[3], b[4]
    if ka == 'rect' and kb == 'rect': return 1e9
    if ka == 'rect': a, b = b, a; ka, ga, ra, kb, gb, rb = kb, gb, rb, ka, ga, ra
    if kb == 'seg':
        return seg_seg(*ga, *gb) - ra - rb
    x0, y0, x1, y1 = gb
    (p, q) = ga
    inside = lambda pt: x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1
    if inside(p) or inside(q): return -ra
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    return min(seg_seg(p, q, *e) for e in edges) - ra

S = shapes()
bad = []
for L in LAYERS:
    items = [s for s in S if s[0] == L]
    routed = [s for s in items if s[5]]
    for a in routed:
        for b in items:
            if b is a or b[1] == a[1]: continue
            if b[5] and id(b) < id(a): continue
            need = max(clearance_of(a[1]), clearance_of(b[1]) if not b[1].startswith('~') else 0.2)
            d = dist(a, b)
            if d < need - 0.005:
                bad.append((round(d, 3), need, L, a[1], b[1], a[3] if a[2] == 'seg' else '', b[3]))
bad.sort()
print('exact clearance violations:', len(bad))
for x in bad[:30]: print(' ', x)
