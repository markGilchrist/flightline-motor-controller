import math, copy
from fplib import load, bbox
from design import PARTS, OX, OY

def rot(x, y, a):
    """KiCad footprint rotation (CCW on screen, y down)."""
    r = math.radians(a)
    return x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)

_cache = {}
def fp_of(lib):
    if lib not in _cache:
        _cache[lib] = load(lib)
    return copy.deepcopy(_cache[lib])

def circ_bbox(fp):
    xs, ys = [], []
    for g in fp.graphicItems:
        if getattr(g, 'layer', None) == 'F.CrtYd':
            if type(g).__name__ == 'FpCircle':
                r = math.hypot(g.end.X - g.center.X, g.end.Y - g.center.Y)
                xs += [g.center.X - r, g.center.X + r]; ys += [g.center.Y - r, g.center.Y + r]
            else:
                for a in ('start', 'end'):
                    p = getattr(g, a, None)
                    if p is not None: xs.append(p.X); ys.append(p.Y)
                for p in (getattr(g, 'coordinates', None) or []):
                    xs.append(p.X); ys.append(p.Y)
    if not xs:
        return bbox(fp)
    return min(xs), min(ys), max(xs), max(ys)

def pad_list(part):
    """Absolute pads: dict(ref, num, net, x, y, w, h, shape, type, drill, rr) with w/h already rotated (0/90/180/270 only)."""
    fp = fp_of(part['fp'])
    out = []
    for p in fp.pads:
        lx, ly = p.position.X, p.position.Y
        dx, dy = rot(lx, ly, part['rot'])
        a = (part['rot'] + (p.position.angle or 0)) % 180
        w, h = (p.size.X, p.size.Y) if abs(a) < 1 else (p.size.Y, p.size.X)
        num = str(p.number)
        net = part['pins'].get(num) if num else None
        drill = p.drill.diameter if p.drill is not None else 0
        out.append(dict(ref=part['ref'], num=num, net=net, x=part['x'] + dx, y=part['y'] + dy, w=w, h=h,
                        shape=p.shape, type=p.type, layers=p.layers, drill=drill,
                        rr=getattr(p, 'roundrectRatio', None)))
    return out

def courtyard(part):
    fp = fp_of(part['fp'])
    x0, y0, x1, y1 = circ_bbox(fp)
    pts = [rot(x, y, part['rot']) for x, y in ((x0, y0), (x1, y1))]
    xs = [part['x'] + p[0] for p in pts]; ys = [part['y'] + p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def all_pads():
    res = []
    for p in PARTS:
        res += pad_list(p)
    return res
