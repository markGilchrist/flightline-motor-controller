"""Add GND stitching vias where both copper layers are solid GND pour (simulated), on a 4 mm grid."""
import json, sys, numpy as np, cv2
import check
from design import W, H

def stitch(routes_path, out_path, pitch=5.0, size=0.6, drill=0.3):
    rep = check.run(routes_path, verbose=False)
    full, nid = rep['_full'], rep['_nid']
    g = nid['GND']
    both = ((full['F.Cu'] == g) & (full['B.Cu'] == g)).astype(np.uint8)
    r = int(round((size / 2 + 0.45) / check.RES))   # via radius + pour min width margin
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    safe = cv2.erode(both, k)
    routes = json.load(open(routes_path))
    existing = [(v[1], v[2]) for v in routes['vias'] + routes.get('fix_vias', [])]
    new = []
    y = 2.5
    while y < H - 1.5:
        x = 2.5
        while x < W - 1.5:
            if safe[check.px(y), check.px(x)] and all((x - a) ** 2 + (y - b) ** 2 > 2.0 ** 2 for a, b in existing + new):
                new.append((x, y))
            x += pitch
        y += pitch
    routes['stitch'] = [['GND', round(x, 3), round(y, 3), size, drill] for x, y in new]
    json.dump(routes, open(out_path, 'w'))
    print('stitching vias:', len(new))

if __name__ == '__main__':
    stitch(sys.argv[1], sys.argv[2])
