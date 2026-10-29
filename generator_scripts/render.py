"""Matplotlib render of placement + routing with real track widths. usage: render.py out.png [x0 y0 x1 y1]"""
import sys, json
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
from design import PARTS, W, H
from geom import pad_list, courtyard
from check import load_items

def render(path, win=None, routes='out/routes.json', labels=True):
    tracks, vias = load_items(routes)
    x0, y0, x1, y1 = win or (-1, -1, W + 1, H + 1)
    s = 120 / max(x1 - x0, y1 - y0) * 1.0
    fig, ax = plt.subplots(figsize=((x1 - x0) * s / 10, (y1 - y0) * s / 10), dpi=100)
    ax.add_patch(Rectangle((0, 0), W, H, fc='#0b3d1e', ec='y', lw=1))
    pts_per_mm = fig.dpi * (x1 - x0) * s / 10 / (x1 - x0) * 72 / fig.dpi
    for t in [t for t in tracks if t['layer'] == 'B.Cu'] + [t for t in tracks if t['layer'] == 'F.Cu']:
        col = '#d33' if t['layer'] == 'F.Cu' else '#39f'
        ax.plot([t['x1'], t['x2']], [t['y1'], t['y2']], color=col, lw=t['w'] * pts_per_mm,
                solid_capstyle='round', alpha=0.65 if t['layer'] == 'F.Cu' else 0.55)
    for p in PARTS:
        cx0, cy0, cx1, cy1 = courtyard(p)
        ax.add_patch(Rectangle((cx0, cy0), cx1 - cx0, cy1 - cy0, fill=False, ec='#ccc', lw=0.4, ls='--'))
        for pd in pad_list(p):
            c = '#e8b84a' if pd['type'] != 'np_thru_hole' else '#222'
            if pd['shape'] in ('circle',):
                ax.add_patch(Circle((pd['x'], pd['y']), pd['w'] / 2, fc=c, alpha=0.85))
            else:
                ax.add_patch(Rectangle((pd['x'] - pd['w'] / 2, pd['y'] - pd['h'] / 2), pd['w'], pd['h'], fc=c, alpha=0.85))
            if labels and pd['net'] and x0 <= pd['x'] <= x1 and y0 <= pd['y'] <= y1:
                ax.text(pd['x'], pd['y'], f"{pd['num']}\n{pd['net']}", fontsize=max(3, 0.35 * s), ha='center', va='center', color='k')
        if x0 <= (cx0 + cx1) / 2 <= x1 and y0 <= cy0 <= y1:
            ax.text((cx0 + cx1) / 2, cy0 - 0.2, p['ref'], fontsize=max(4, 0.5 * s), ha='center', va='bottom', color='w')
    for v in vias:
        ax.add_patch(Circle((v['x'], v['y']), v['s'] / 2, fc='#bbb', ec='k', lw=0.3))
        ax.add_patch(Circle((v['x'], v['y']), v['d'] / 2, fc='k'))
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect('equal')
    ax.grid(True, lw=0.2, alpha=0.4)
    fig.savefig(path, bbox_inches='tight', facecolor='w'); plt.close(fig)

if __name__ == '__main__':
    a = sys.argv[1:]
    render(a[0], tuple(map(float, a[1:5])) if len(a) >= 5 else None)
