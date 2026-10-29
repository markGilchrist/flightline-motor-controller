"""Raster DRC + connectivity check (0.025 mm grid).
Draws every pad/track/via per copper layer, simulates the GND pours the way KiCad fills them
(board minus other-net copper grown by the zone clearance, minus keepouts, islands removed),
then reports: unconnected pads per net, shorts, clearance violations, track-to-edge issues."""
import json, sys, math
import numpy as np, cv2
from scipy import ndimage
from design import PARTS, W, H, NETCLASS
from geom import all_pads
import power_routes

RES = 0.025                      # mm per pixel
PAD = 1.0                        # mm margin around board in the raster
NX, NY = int((W + 2 * PAD) / RES), int((H + 2 * PAD) / RES)
LAYERS = ('F.Cu', 'B.Cu')
ZONE_CLR, ZONE_MIN = 0.4, 0.25
ANTENNA = (56.0, -1.0, 78.0, 7.4)  # no copper (pour) here on either layer

def px(v): return int(round((v + PAD) / RES))

def clearance_of(net):
    for c in NETCLASS.values():
        if net in c.get('nets', []): return c['clearance']
    return NETCLASS['Default']['clearance']

def draw_pad(img, pd, val, grow=0.0):
    x, y, w, h = pd['x'], pd['y'], pd['w'] + 2 * grow, pd['h'] + 2 * grow
    if pd['shape'] == 'circle':
        cv2.circle(img, (px(x), px(y)), max(1, int(round(w / 2 / RES))), val, -1)
    elif pd['shape'] == 'oval':
        r = min(w, h) / 2
        if w >= h: a, b = (x - w / 2 + r, y), (x + w / 2 - r, y)
        else: a, b = (x, y - h / 2 + r), (x, y + h / 2 - r)
        cv2.line(img, (px(a[0]), px(a[1])), (px(b[0]), px(b[1])), val, max(1, int(round(2 * r / RES))))
        cv2.circle(img, (px(a[0]), px(a[1])), int(round(r / RES)), val, -1)
        cv2.circle(img, (px(b[0]), px(b[1])), int(round(r / RES)), val, -1)
    else:
        rr = (pd['rr'] or 0) * min(pd['w'], pd['h']) if pd['shape'] == 'roundrect' else 0
        rr += grow
        x0, y0, x1, y1 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
        if rr <= RES:
            cv2.rectangle(img, (px(x0), px(y0)), (px(x1) - 1, px(y1) - 1), val, -1)
        else:
            cv2.rectangle(img, (px(x0 + rr), px(y0)), (px(x1 - rr) - 1, px(y1) - 1), val, -1)
            cv2.rectangle(img, (px(x0), px(y0 + rr)), (px(x1) - 1, px(y1 - rr) - 1), val, -1)
            for cx, cy in ((x0 + rr, y0 + rr), (x1 - rr, y0 + rr), (x0 + rr, y1 - rr), (x1 - rr, y1 - rr)):
                cv2.circle(img, (px(cx), px(cy)), int(round(rr / RES)), val, -1)

def draw_track(img, t, val, grow=0.0):
    w = t['w'] + 2 * grow
    th = max(1, int(round(w / RES)))
    cv2.line(img, (px(t['x1']), px(t['y1'])), (px(t['x2']), px(t['y2'])), val, th)
    for X, Y in ((t['x1'], t['y1']), (t['x2'], t['y2'])):
        cv2.circle(img, (px(X), px(Y)), int(round(w / 2 / RES)), val, -1)

def pad_layers(pd):
    if pd['type'] in ('thru_hole',) or '*.Cu' in pd['layers']: return LAYERS
    return tuple(l for l in LAYERS if l in pd['layers'])

def load_items(routes_path='out/routes.json'):
    tracks, vias = [], []
    for net, layer, w, poly in power_routes.TRACKS:
        for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
            tracks.append(dict(net=net, layer=layer, w=w, x1=x1, y1=y1, x2=x2, y2=y2))
    for net, x, y, s, d in power_routes.all_vias():
        vias.append(dict(net=net, x=x, y=y, s=s, d=d))
    try:
        r = json.load(open(routes_path))
        for net, layer, w, x1, y1, x2, y2 in r['tracks']:
            tracks.append(dict(net=net, layer=layer, w=w, x1=x1, y1=y1, x2=x2, y2=y2))
        for net, layer, w, x1, y1, x2, y2 in r.get('fix_tracks', []):
            tracks.append(dict(net=net, layer=layer, w=w, x1=x1, y1=y1, x2=x2, y2=y2))
        for net, x, y, s, d in r['vias'] + r.get('fix_vias', []) + r.get('stitch', []):
            vias.append(dict(net=net, x=x, y=y, s=s, d=d))
    except FileNotFoundError:
        pass
    return tracks, vias

def run(routes_path='out/routes.json', verbose=True, save=None):
    pads = [p for p in all_pads()]
    tracks, vias = load_items(routes_path)
    nets = sorted({p['net'] for p in pads if p['net']} | {t['net'] for t in tracks})
    nid = {n: i + 1 for i, n in enumerate(nets)}
    gnd = nid['GND']
    board = np.zeros((NY, NX), np.uint8)
    cv2.rectangle(board, (px(0), px(0)), (px(W) - 1, px(H) - 1), 1, -1)
    report = dict(shorts=[], clearance=[], unconnected={}, edge=[])

    # per-layer net id raster ("explicit" copper: pads, tracks, vias)
    copper = {L: np.zeros((NY, NX), np.int16) for L in LAYERS}
    routed = {L: np.zeros((NY, NX), np.uint8) for L in LAYERS}   # tracks + vias only
    holes = np.zeros((NY, NX), np.uint8)
    def put(L, draw, n):
        m = np.zeros((NY, NX), np.uint8); draw(m, 1)
        clash = (copper[L] != 0) & (copper[L] != n) & (m == 1)
        if clash.any():
            others = set(np.unique(copper[L][clash]).tolist())
            report['shorts'].append((L, nets[n - 1], [nets[o - 1] for o in others]))
        copper[L][m == 1] = n
    for pd in pads:
        if pd['type'] == 'np_thru_hole':
            draw_pad(holes, dict(pd, shape='circle', w=max(pd['drill'], pd['w']), h=max(pd['drill'], pd['w'])), 1)
            continue
        n = nid.get(pd['net'], -1) if pd['net'] else -1   # -1 = unconnected pad (still copper)
        for L in pad_layers(pd):
            put(L, lambda m, v, pd=pd: draw_pad(m, pd, v), n)
    for t in tracks:
        put(t['layer'], lambda m, v, t=t: draw_track(m, t, v), nid[t['net']])
        draw_track(routed[t['layer']], t, 1)
    for v in vias:
        for L in LAYERS:
            cv2.circle(routed[L], (px(v['x']), px(v['y'])), int(round(v['s'] / 2 / RES)), 1, -1)
            put(L, lambda m, val, v=v: cv2.circle(m, (px(v['x']), px(v['y'])), int(round(v['s'] / 2 / RES)), val, -1), nid[v['net']])

    # clearance check between different nets on the same layer (grown by half the larger clearance each side)
    for L in LAYERS:
        c = copper[L]
        for n in nets:
            i = nid[n]
            mask = (c == i).astype(np.uint8)
            if not mask.any(): continue
            r = int(round((clearance_of(n) - 0.03) / RES))
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            grown = cv2.dilate(mask, k)
            grown_r = cv2.dilate(mask & routed[L], k)
            other = (c != 0) & (c != i)
            # pad-to-pad gaps inside a footprint are set by the footprint, so only flag routed copper
            bad = ((grown == 1) & other & (routed[L] == 1)) | ((grown_r == 1) & other)
            if bad.any():
                others = set(np.unique(c[bad]).tolist())
                for o in others:
                    if o > i or o < 0:
                        oname = nets[o - 1] if o > 0 else '(no-net pad)'
                        ys, xs = np.nonzero(bad & (c == o))
                        report['clearance'].append((L, n, oname, round(xs.mean() * RES - PAD, 2), round(ys.mean() * RES - PAD, 2)))
        # copper to board edge (0.3 mm)
        e = int(round(0.3 / RES))
        inner = cv2.erode(board, np.ones((2 * e + 1, 2 * e + 1), np.uint8))
        bad = (c != 0) & (inner == 0)
        if bad.any():
            ys, xs = np.nonzero(bad)
            report['edge'].append((L, len(xs), round(xs.mean() * RES - PAD, 2), round(ys.mean() * RES - PAD, 2)))

    # GND pour simulation
    full = {}
    for L in LAYERS:
        c = copper[L]
        other = ((c != 0) & (c != gnd)).astype(np.uint8)
        r = int(round(ZONE_CLR / RES))
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        avoid = cv2.dilate(other | holes, k)
        m = int(round(0.3 / RES))
        area = np.zeros_like(board); cv2.rectangle(area, (px(m * RES), px(m * RES)), (px(W - m * RES) - 1, px(H - m * RES) - 1), 1, -1)
        x0, y0, x1, y1 = ANTENNA
        cv2.rectangle(area, (px(x0), px(max(y0, -PAD))), (px(x1), px(y1)), 0, -1)
        pour = (area == 1) & (avoid == 0)
        mt = int(round(ZONE_MIN / 2 / RES))
        km = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * mt + 1, 2 * mt + 1))
        pour = cv2.morphologyEx(pour.astype(np.uint8), cv2.MORPH_OPEN, km).astype(bool)
        fl = c.copy()
        fl[pour & (fl == 0)] = gnd
        full[L] = fl

    # island removal for GND fill: keep pour islands that touch explicit GND copper
    for L in LAYERS:
        g = full[L] == gnd
        lab, n = ndimage.label(g)
        keep = np.unique(lab[(copper[L] == gnd) & g])
        keepmask = np.isin(lab, keep[keep > 0])
        full[L][g & ~keepmask] = 0

    # connectivity: per net components across layers via vias and THT pads
    lab = {}
    offset = 0
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent.setdefault(parent[a], parent[a]); a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    for L in LAYERS:
        l = np.zeros((NY, NX), np.int32)
        for n in nets:
            mk = full[L] == nid[n]
            if not mk.any(): continue
            ll, k = ndimage.label(mk)
            l[mk] = ll[mk] + offset
            offset += k
        lab[L] = l
    def at(L, x, y):
        return int(lab[L][px(y), px(x)]) if 0 <= px(y) < NY and 0 <= px(x) < NX else 0
    for v in vias:
        a, b = at('F.Cu', v['x'], v['y']), at('B.Cu', v['x'], v['y'])
        if a and b: union(a, b)
    for pd in pads:
        if pd['type'] == 'thru_hole' and pd['net']:
            a, b = at('F.Cu', pd['x'], pd['y']), at('B.Cu', pd['x'], pd['y'])
            if a and b: union(a, b)
    # pads with same ref+number+net are internally connected (e.g. split pads, EPAD vias)
    groups = {}
    for pd in pads:
        if not pd['net']: continue
        L = pad_layers(pd)[0]
        comp = at(L, pd['x'], pd['y'])
        groups.setdefault((pd['ref'], pd['num']), []).append(comp)
    for comps in groups.values():
        for a in comps[1:]:
            if a and comps[0]: union(a, comps[0])
    for n in nets:
        comps = {}
        for pd in pads:
            if pd['net'] != n: continue
            L = pad_layers(pd)[0]
            c = at(L, pd['x'], pd['y'])
            comps.setdefault(find(c) if c else None, []).append(f"{pd['ref']}.{pd['num']}")
        if len(comps) > 1:
            # largest group is "main"; list the rest
            ordered = sorted(comps.values(), key=len, reverse=True)
            report['unconnected'][n] = [sorted(set(g)) for g in ordered[1:]]
    if save:
        img = np.full((NY, NX, 3), 255, np.uint8)
        img[board == 1] = (30, 90, 30)
        img[full['B.Cu'] != 0] = (200, 120, 40)
        img[full['B.Cu'] == gnd] = (150, 100, 60)
        f = full['F.Cu']
        img[(f != 0)] = (40, 40, 200)
        img[f == gnd] = (60, 60, 150)
        img[holes == 1] = (0, 0, 0)
        cv2.imwrite(save, img[::2, ::2])
    report['_full'] = full; report['_nid'] = nid; report['_holes'] = holes
    if verbose:
        print('shorts:', report['shorts'])
        print('clearance violations:', len(report['clearance']))
        for c in report['clearance'][:60]: print('  ', c)
        print('edge:', report['edge'])
        print('unconnected:', json.dumps(report['unconnected'], indent=1))
    return report

if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'out/routes.json', save='out/check.png')
