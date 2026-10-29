import sys, itertools
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
from design import PARTS, W, H
from geom import pad_list, courtyard

def draw(ax, tracks=(), vias=(), show_ref=True, layer_alpha=None):
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec='k', lw=1.5))
    cols = {}
    palette = plt.cm.tab20.colors
    for p in PARTS:
        x0, y0, x1, y1 = courtyard(p)
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec='#999', lw=0.5, ls='--'))
        for pd in pad_list(p):
            c = '#c33' if pd['type'] == 'smd' else '#c90'
            if pd['net'] is None: c = '#888'
            if pd['shape'] == 'circle':
                ax.add_patch(Circle((pd['x'], pd['y']), pd['w'] / 2, color=c, alpha=0.8))
            else:
                ax.add_patch(Rectangle((pd['x'] - pd['w'] / 2, pd['y'] - pd['h'] / 2), pd['w'], pd['h'], color=c, alpha=0.8))
            if pd['net'] and pd['w'] > 1.6 and pd['h'] > 1.6:
                ax.text(pd['x'], pd['y'], pd['net'], fontsize=3, ha='center', va='center')
        if show_ref:
            ax.text((x0 + x1) / 2, y0 - 0.3, p['ref'], fontsize=5, ha='center', va='bottom', color='navy')
    for t in tracks:
        col = '#d22' if t['layer'] == 'F.Cu' else '#22d'
        ax.plot([t['x1'], t['x2']], [t['y1'], t['y2']], color=col, lw=t['w'] * 72 / 25.4 * ax.figure.dpi / 72 * 0.0 + 0.1,
                solid_capstyle='round', alpha=0.5)
    ax.set_xlim(-2, W + 2); ax.set_ylim(H + 2, -2); ax.set_aspect('equal')

def overlaps():
    res = []
    cy = {p['ref']: courtyard(p) for p in PARTS}
    for a, b in itertools.combinations(PARTS, 2):
        A, B = cy[a['ref']], cy[b['ref']]
        if A[0] < B[2] and B[0] < A[2] and A[1] < B[3] and B[1] < A[3]:
            res.append((a['ref'], b['ref']))
    out = []
    for p in PARTS:
        x0, y0, x1, y1 = cy[p['ref']]
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H: out.append(p['ref'])
    return res, out

if __name__ == '__main__':
    fig, ax = plt.subplots(figsize=(14, 12), dpi=110)
    draw(ax)
    fig.savefig(sys.argv[1] if len(sys.argv) > 1 else 'place.png', bbox_inches='tight')
    ov, out = overlaps()
    print('overlaps:', ov); print('outside:', out)
