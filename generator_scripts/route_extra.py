"""Route a few extra connections onto the finished board with a two-layer grid A* router.

Usage: python3 route_extra.py board.kicad_pcb routes_in.json routes_out.json
  board.kicad_pcb  built by build_pcb.py from routes_in.json, already containing the new parts
  routes_out.json  routes_in.json plus the new tracks/vias (stored as locked fix_tracks/fix_vias),
                   minus any GND stitching via that collides with the new copper

Freerouting is the main router (route.py); this is for small additions after the main route is frozen,
so the existing copper is left untouched. Everything other nets own is an obstacle, inflated by the
larger of the two net classes' clearances. Stitching vias are treated as removable. The result must still
pass KiCad DRC (kicad_finish.py).
"""
import sys, json, math, heapq, time
import numpy as np
from PIL import Image, ImageDraw
import pcbnew
from design import W, H, OX, OY, NETCLASS

# (net, (ref, pad), (ref, pad)) in routing order
CONNECTIONS = [
    ('PARK', ('R17', '2'), ('J5', '1')),
    ('PARK', ('J5', '1'), ('R18', '1')),
    ('PARK_ADC', ('R18', '2'), ('R19', '1')),
    ('PARK_ADC', ('R19', '1'), ('C18', '1')),
    ('PARK_ADC', ('R18', '2'), ('U3', '7')),
]
G = 0.1                   # grid (mm)
GRID_MARGIN = 0.06        # extra clearance so diagonal grid steps never end up too close
WINDOW = 8.0              # search only this far (mm) outside the endpoints' bounding box
EDGE = 0.5                # copper to board edge
VIA_COST, BOTTOM_COST = 40, 1.4   # discourage vias and bottom-layer runs (keep the bottom GND pour whole)

def netclass(net):
    for name, nc in NETCLASS.items():
        if net in nc.get('nets', []):
            return nc
    return NETCLASS['Default']

def clearance(a, b):
    return max(netclass(a)['clearance'], netclass(b)['clearance'])

def main(pcb_path, rin, rout):
    routes = json.load(open(rin))
    b = pcbnew.LoadBoard(pcb_path)
    nx, ny = int(W / G) + 1, int(H / G) + 1
    to_px = lambda x, y: ((x / 1e6 - OX) / G, (y / 1e6 - OY) / G)
    stitch = {(round(v[1], 3), round(v[2], 3)) for v in routes.get('stitch', [])}
    LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

    def obstacle_maps(net, extra_tracks, half):
        """Per layer: True where a track of this net (half width `half`) or a via may not be centred."""
        imgs = [Image.new('1', (nx, ny), 0) for _ in LAYERS]
        draws = [ImageDraw.Draw(i) for i in imgs]
        def disc(li, x, y, r):          # x, y, r in pcbnew units (nm)
            px, py = to_px(x, y); rr = r / 1e6 / G
            draws[li].ellipse([px - rr, py - rr, px + rr, py + rr], fill=1)
        def seg(li, x1, y1, x2, y2, r):
            a, c = to_px(x1, y1), to_px(x2, y2)
            draws[li].line([a, c], fill=1, width=max(1, int(round(2 * r / 1e6 / G))))
            disc(li, x1, y1, r); disc(li, x2, y2, r)
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() == net:
                    continue
                infl = clearance(net, pad.GetNetname() or 'Default') + half + GRID_MARGIN
                for li, L in enumerate(LAYERS):
                    if not pad.IsOnLayer(L):
                        continue
                    poly = pad.GetEffectivePolygon().CloneDropTriangulation() if hasattr(pad.GetEffectivePolygon(), 'CloneDropTriangulation') else pad.GetEffectivePolygon()
                    sp = pcbnew.SHAPE_POLY_SET(poly)
                    sp.Inflate(int(infl * 1e6), 16)
                    for k in range(sp.OutlineCount()):
                        o = sp.Outline(k)
                        draws[li].polygon([to_px(o.CPoint(j).x, o.CPoint(j).y) for j in range(o.PointCount())], fill=1)
                if pad.GetDrillSize().x > 0:     # holes block both layers
                    for li in range(2):
                        disc(li, pad.GetPosition().x, pad.GetPosition().y, pad.GetDrillSize().x / 2 + (0.25 + half) * 1e6)
        for t in b.GetTracks():
            if t.GetNetname() == net:
                continue
            infl = clearance(net, t.GetNetname()) + half + GRID_MARGIN
            if t.GetClass() == 'PCB_VIA':
                key = (round(t.GetPosition().x / 1e6 - OX, 3), round(t.GetPosition().y / 1e6 - OY, 3))
                if t.GetNetname() == 'GND' and key in stitch:
                    continue                                   # removable
                for li in range(2):
                    disc(li, t.GetPosition().x, t.GetPosition().y, t.GetWidth() / 2 + infl * 1e6)
            else:
                li = 0 if t.GetLayer() == pcbnew.F_Cu else 1
                seg(li, t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetWidth() / 2 + infl * 1e6)
        for n2, layer, w, x1, y1, x2, y2 in extra_tracks:          # connections routed earlier in this run
            if n2 == net:
                continue
            li = 0 if layer == 'F.Cu' else 1
            r = (w / 2 + clearance(net, n2) + half + GRID_MARGIN) * 1e6
            seg(li, (x1 + OX) * 1e6, (y1 + OY) * 1e6, (x2 + OX) * 1e6, (y2 + OY) * 1e6, r)
        for z in b.Zones():                                        # rule areas (antenna keepout)
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                o = z.Outline().Outline(0)
                for li in range(2):
                    draws[li].polygon([to_px(o.CPoint(j).x, o.CPoint(j).y) for j in range(o.PointCount())], fill=1)
        for fp in b.GetFootprints():
            for z in fp.Zones():
                if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                    o = z.Outline().Outline(0)
                    for li in range(2):
                        draws[li].polygon([to_px(o.CPoint(j).x, o.CPoint(j).y) for j in range(o.PointCount())], fill=1)
        m = [np.array(i, dtype=bool) for i in imgs]
        e = int(math.ceil((EDGE + half) / G))
        for a in m:
            a[:e, :] = a[-e:, :] = True; a[:, :e] = a[:, -e:] = True
        return m

    def pad_cells(ref, num, net, block):
        fp = b.FindFootprintByReference(ref)
        cells = []
        for pad in fp.Pads():
            if pad.GetNumber() != num:
                continue
            for li, L in enumerate(LAYERS):
                if not pad.IsOnLayer(L):
                    continue
                bb = pad.GetBoundingBox()
                x0, y0 = to_px(bb.GetX(), bb.GetY()); x1, y1 = to_px(bb.GetRight(), bb.GetBottom())
                for gy in range(int(y0), int(y1) + 1):
                    for gx in range(int(x0), int(x1) + 1):
                        p = pcbnew.VECTOR2I(int((gx * G + OX) * 1e6), int((gy * G + OY) * 1e6))
                        if pad.HitTest(p) and not block[li][gy, gx]:
                            cells.append((li, gy, gx))
        return cells

    new_tracks, new_vias = [], []
    for net, (ra, pa), (rb, pb) in CONNECTIONS:
        nc = netclass(net)
        half = nc['width'] / 2
        vd, vdr = nc['via']
        t0 = time.time()
        block = obstacle_maps(net, new_tracks, half)
        vblock = obstacle_maps(net, new_tracks, vd / 2)
        print(f'  maps {time.time() - t0:.1f}s', flush=True); t0 = time.time()
        vok = ~(vblock[0] | vblock[1])
        src = pad_cells(ra, pa, net, block)
        dst = set(pad_cells(rb, pb, net, block))
        # tracks already routed for this net are part of the source tree: the new branch may start anywhere on it
        src = set(src)
        for n2, layer, w, x1, y1, x2, y2 in new_tracks:
            if n2 != net:
                continue
            li = 0 if layer == 'F.Cu' else 1
            steps = max(1, int(math.hypot(x2 - x1, y2 - y1) / G))
            for k in range(steps + 1):
                gx = int(round((x1 + (x2 - x1) * k / steps) / G)); gy = int(round((y1 + (y2 - y1) * k / steps) / G))
                if not block[li][gy, gx]:
                    src.add((li, gy, gx))
        src -= dst
        print(f'  endpoints {len(src)}/{len(dst)} {time.time() - t0:.1f}s', flush=True); t0 = time.time()
        if not src or not dst:
            sys.exit(f'{net}: no free cells on {ra}.{pa} or {rb}.{pb}')
        tx = np.mean([c[2] for c in dst]); ty = np.mean([c[1] for c in dst])
        allc = list(src) + list(dst); wm = int(WINDOW / G)
        wy0 = max(0, min(c[1] for c in allc) - wm); wy1 = min(ny - 1, max(c[1] for c in allc) + wm)
        wx0 = max(0, min(c[2] for c in allc) - wm); wx1 = min(nx - 1, max(c[2] for c in allc) + wm)
        hfun = lambda gy, gx: math.hypot(gx - tx, gy - ty) * 0.999
        openq, came, cost = [], {}, {}
        for c in src:
            cost[c] = 0; heapq.heappush(openq, (hfun(c[1], c[2]), 0, c))
        found = None
        DIRS = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.4142), (1, 1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142)]
        while openq:
            f, g, c = heapq.heappop(openq)
            if g > cost.get(c, 1e18):
                continue
            if c in dst:
                found = c; break
            li, gy, gx = c
            for dy, dx, w in DIRS:
                n = (li, gy + dy, gx + dx)
                if not (wy0 <= n[1] <= wy1 and wx0 <= n[2] <= wx1) or block[li][n[1], n[2]]:
                    continue
                ng = g + w * (BOTTOM_COST if li == 1 else 1)
                prev = came.get(c)                                  # small penalty for turning
                if prev and prev[0] == li and (gy - prev[1], gx - prev[2]) != (dy, dx):
                    ng += 0.3
                if ng < cost.get(n, 1e18):
                    cost[n] = ng; came[n] = c; heapq.heappush(openq, (ng + hfun(n[1], n[2]), ng, n))
            if vok[gy, gx]:
                n = (1 - li, gy, gx)
                if not block[n[0]][gy, gx]:
                    ng = g + VIA_COST
                    if ng < cost.get(n, 1e18):
                        cost[n] = ng; came[n] = c; heapq.heappush(openq, (ng + hfun(gy, gx), ng, n))
        if not found:
            sys.exit(f'{net}: no route {ra}.{pa} -> {rb}.{pb}')
        path = [found]
        while path[-1] in came:
            path.append(came[path[-1]])
        path.reverse()
        # turn the cell path into straight segments and vias
        runs = [[path[0]]]
        for c in path[1:]:
            if c[0] != runs[-1][-1][0]:
                new_vias.append((net, round(c[2] * G, 3), round(c[1] * G, 3), vd, vdr))
                runs.append([c])
            else:
                runs[-1].append(c)
        for run in runs:
            layer = 'F.Cu' if run[0][0] == 0 else 'B.Cu'
            pts = [(c[2] * G, c[1] * G) for c in run]
            keep = [pts[0]]
            for i in range(1, len(pts) - 1):
                d1 = (pts[i][0] - keep[-1][0], pts[i][1] - keep[-1][1]); d2 = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                if abs(d1[0] * d2[1] - d1[1] * d2[0]) > 1e-9:
                    keep.append(pts[i])
            keep.append(pts[-1])
            for (x1, y1), (x2, y2) in zip(keep, keep[1:]):
                new_tracks.append((net, layer, nc['width'], round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)))
        print(f'{net} {ra}.{pa} -> {rb}.{pb}: {len(path)} cells, {len(runs) - 1} vias', flush=True)

    # drop stitching vias that now collide with new copper or the new parts' pads
    def too_close(x, y, r):
        for net, layer, w, x1, y1, x2, y2 in new_tracks:
            dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
            t = 0 if L2 == 0 else max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / L2))
            if math.hypot(x - x1 - t * dx, y - y1 - t * dy) < r + w / 2 + 0.25:
                return True
        for net, vx, vy, s, d in new_vias:
            if math.hypot(x - vx, y - vy) < r + s / 2 + 0.25:
                return True
        p = pcbnew.VECTOR2I(int((x + OX) * 1e6), int((y + OY) * 1e6))
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname() != 'GND' and pad.HitTest(p, int((r + 0.3) * 1e6)):
                    return True
        return False
    kept = [v for v in routes['stitch'] if not too_close(v[1], v[2], v[3] / 2)]
    print('stitching vias removed:', len(routes['stitch']) - len(kept), [(v[1], v[2]) for v in routes['stitch'] if v not in kept])
    routes['stitch'] = kept
    routes['fix_tracks'] = routes.get('fix_tracks', []) + [list(t) for t in new_tracks]
    routes['fix_vias'] = routes.get('fix_vias', []) + [list(v) for v in new_vias]
    json.dump(routes, open(rout, 'w'))
    print('wrote', rout, len(new_tracks), 'tracks', len(new_vias), 'vias')

if __name__ == '__main__':
    main(*sys.argv[1:4])
    import os; os._exit(0)
