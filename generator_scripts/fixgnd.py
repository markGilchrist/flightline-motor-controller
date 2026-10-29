"""For every GND pad cut off from the main ground, add a short top track + via down to the bottom pour."""
import json, sys, math, numpy as np, cv2
from scipy import ndimage
import check
from geom import all_pads

def solve(routes_path, out_path, rounds=3):
    routes = json.load(open(routes_path))
    routes.setdefault('fix_tracks', []); routes.setdefault('fix_vias', [])
    for rnd in range(rounds):
        json.dump(routes, open(out_path, 'w'))
        rep = check.run(out_path, verbose=False)
        iso = rep['unconnected'].get('GND', [])
        if not iso:
            print('GND fully connected after', rnd, 'fix rounds'); return routes
        full, nid = rep['_full'], rep['_nid']; g = nid['GND']
        top, bot = full['F.Cu'], full['B.Cu']
        # main bottom GND component = largest
        lab, n = ndimage.label(bot == g)
        sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
        main = int(np.argmax(sizes)) + 1
        pads = {f"{p['ref']}.{p['num']}": p for p in all_pads() if p['net'] == 'GND'}
        R = check.RES
        def disk_ok(img, x, y, r, ok):
            rr = int(math.ceil(r / R)); cx, cy = check.px(x), check.px(y)
            win = img[cy - rr:cy + rr + 1, cx - rr:cx + rr + 1]
            yy, xx = np.mgrid[-rr:rr + 1, -rr:rr + 1]
            m = xx ** 2 + yy ** 2 <= rr ** 2
            return bool(ok(win[m]).all())
        for group in iso:
            pd = pads[group[0]]
            best = None
            for dx in np.arange(-3.0, 3.01, 0.1):
                for dy in np.arange(-3.0, 3.01, 0.1):
                    d = math.hypot(dx, dy)
                    if d < 0.5 or (best and d >= best[0]): continue
                    x, y = pd['x'] + dx, pd['y'] + dy
                    if not (1 < x < check.W - 1 and 1 < y < check.H - 1): continue
                    # bottom: via + 0.3 clearance entirely in the main GND pour
                    if not disk_ok(lab, x, y, 0.3 + 0.3, lambda v: v == main): continue
                    # top: via + clearance free of other nets
                    if not disk_ok(top, x, y, 0.3 + 0.25, lambda v: (v == 0) | (v == g)): continue
                    # top: 0.4 mm track from pad centre to via, clearance 0.25
                    ok = True
                    for t in np.linspace(0, 1, max(2, int(d / 0.1))):
                        if not disk_ok(top, pd['x'] + dx * t, pd['y'] + dy * t, 0.2 + 0.25, lambda v: (v == 0) | (v == g)):
                            # allow being inside the pad itself
                            if t * d > min(pd['w'], pd['h']) / 2: ok = False; break
                    if ok: best = (d, x, y)
            if best:
                _, x, y = best
                routes['fix_tracks'].append(['GND', 'F.Cu', 0.4, pd['x'], pd['y'], round(x, 3), round(y, 3)])
                routes['fix_vias'].append(['GND', round(x, 3), round(y, 3), 0.6, 0.3])
                print('fix', group, '-> via at', round(x, 2), round(y, 2))
            else:
                print('NO SPOT for', group)
    json.dump(routes, open(out_path, 'w'))
    return routes

if __name__ == '__main__':
    solve(sys.argv[1], sys.argv[2])
