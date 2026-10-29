"""Fab-style renders of both sides: soldermask green, copper (incl. simulated pours), gold pads, white silk refs."""
import numpy as np, cv2
import check
from geom import all_pads, courtyard
from design import PARTS, W, H

rep = check.run('out/routes_final.json', verbose=False)
full = rep['_full']; holes = rep['_holes']
NY, NX = holes.shape
board = np.zeros((NY, NX), np.uint8)
cv2.rectangle(board, (check.px(0), check.px(0)), (check.px(W) - 1, check.px(H) - 1), 1, -1)
tracks, vias = check.load_items('out/routes_final.json')

def side(layer, path, mirror=False):
    img = np.full((NY, NX, 3), 245, np.uint8)
    cu = full[layer] != 0
    img[board == 1] = (40, 95, 25)                # bare laminate under mask (BGR)
    img[(board == 1) & cu] = (60, 150, 60)        # copper under mask
    padmask = np.zeros((NY, NX), np.uint8)
    for p in all_pads():
        if p['type'] == 'np_thru_hole': continue
        if layer in check.pad_layers(p):
            check.draw_pad(padmask, p, 1)
    for v in vias:
        cv2.circle(padmask, (check.px(v['x']), check.px(v['y'])), int(round(v['s'] / 2 / check.RES)), 2, -1)
    img[padmask == 1] = (90, 190, 225)            # ENIG gold
    img[padmask == 2] = (110, 170, 110)           # tented vias
    for p in all_pads():
        if p['type'] in ('thru_hole', 'np_thru_hole') and p['drill']:
            cv2.circle(img, (check.px(p['x']), check.px(p['y'])), int(round(p['drill'] / 2 / check.RES)), (20, 20, 20), -1)
    for v in vias:
        cv2.circle(img, (check.px(v['x']), check.px(v['y'])), int(round(v['d'] / 2 / check.RES)), (20, 20, 20), -1)
    img[holes == 1] = (20, 20, 20)
    if mirror: img = img[:, ::-1].copy()
    # silkscreen reference designators (top only, readable)
    if not mirror:
        for p in PARTS:
            if p['kind'] == 'hole': continue
            x0, y0, x1, y1 = courtyard(p)
            cx = check.px((x0 + x1) / 2); cy = check.px(y0) - 6
            cv2.putText(img, p['ref'], (cx - 9 * len(p['ref']), cy), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        for txt, x, y in (('+12V', 3.5, 63.5), ('GND', 9.3, 63.5), ('MOT-', 77.5, 63.5), ('MOT+', 82.8, 63.5),
                          ('15A', 1.5, 43.5), ('RST', 44.6, 27.8), ('BOOT', 83.0, 27.8)):
            cv2.putText(img, txt, (check.px(x), check.px(y)), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    img = cv2.resize(img, (NX // 2, NY // 2), interpolation=cv2.INTER_AREA)
    cv2.imwrite(path, img)

side('F.Cu', 'out/board_top.png')
side('B.Cu', 'out/board_bottom.png', mirror=True)
print('ok')
