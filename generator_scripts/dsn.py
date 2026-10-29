"""Write a Specctra DSN for Freerouting and read its SES result back (board-relative mm)."""
import re, math
from design import PARTS, W, H, NETCLASS
from geom import pad_list
import power_routes

def um(v): return f'{v * 1000:.1f}'

def cu_layers(pd):
    if '*.Cu' in pd['layers'] or pd['type'] in ('thru_hole',):
        return ['F.Cu', 'B.Cu']
    return [l for l in ('F.Cu', 'B.Cu') if l in pd['layers']]

def padstack_name(pd):
    tht = pd['type'] in ('thru_hole', 'np_thru_hole')
    if not tht and cu_layers(pd) == ['B.Cu']:
        return 'B_' + padstack_name(dict(pd, layers=['F.Cu']))
    sh = pd['shape']
    if sh == 'circle':
        return f"Round[{'A' if tht else 'T'}]Pad_{um(pd['w'])}_um"
    if sh == 'oval':
        return f"Oval[{'A' if tht else 'T'}]Pad_{um(pd['w'])}x{um(pd['h'])}_um"
    return f"Rect[{'A' if tht else 'T'}]Pad_{um(pd['w'])}x{um(pd['h'])}_um"

def padstack_def(name, pd):
    layers = cu_layers(pd)
    w, h = pd['w'], pd['h']
    shapes = []
    for L in layers:
        if pd['shape'] == 'circle':
            shapes.append(f'(shape (circle {L} {um(w)}))')
        elif pd['shape'] == 'oval':
            if w >= h:
                d = (w - h) / 2; shapes.append(f'(shape (path {L} {um(h)} {um(-d)} 0 {um(d)} 0))')
            else:
                d = (h - w) / 2; shapes.append(f'(shape (path {L} {um(w)} 0 {um(-d)} 0 {um(d)}))')
        else:
            shapes.append(f'(shape (rect {L} {um(-w/2)} {um(-h/2)} {um(w/2)} {um(h/2)}))')
    return f'    (padstack "{name}"\n      ' + '\n      '.join(shapes) + '\n      (attach off)\n    )'

def via_name(s, d): return f'Via[0-1]_{um(s)}:{um(d)}_um'

SKIP_NETS = {'GND'}   # connected by the copper pours, not by tracks

def write_dsn(path, route_classes=None):
    lines = []
    A = lines.append
    A('(pcb "motor_ctrl.dsn"')
    A('  (parser (string_quote ") (space_in_quoted_tokens on) (host_cad "KiCad\'s Pcbnew") (host_version "8.0"))')
    A('  (resolution um 10)\n  (unit um)')
    A('  (structure')
    A('    (layer F.Cu (type signal) (property (index 0)))')
    A('    (layer B.Cu (type signal) (property (index 1)))')
    A(f'    (boundary (path pcb 0 0 0 {um(W)} 0 {um(W)} {um(-H)} 0 {um(-H)} 0 0))')
    # keepouts: antenna area (both layers) and mounting holes
    for L in ('F.Cu', 'B.Cu'):
        x0, y0, x1, y1 = 56.0, 0.0, 78.0, 7.4
        A(f'    (keepout "" (polygon {L} 0 {um(x0)} {um(-y0)} {um(x1)} {um(-y0)} {um(x1)} {um(-y1)} {um(x0)} {um(-y1)}))')
        for p in PARTS:
            if p['kind'] == 'hole':
                A(f'    (keepout "" (circle {L} 6400 {um(p["x"])} {um(-p["y"])}))')
    vias = sorted({(v['via'][0], v['via'][1]) for v in NETCLASS.values()} | {(s, dd) for _, _, _, s, dd in power_routes.all_vias()})
    A('    (via ' + ' '.join(f'"{via_name(s, d)}"' for s, d in vias) + ')')
    A('    (rule (width 250) (clearance 200) (clearance 200 (type default_smd)) (clearance 150 (type smd_smd)))')
    A('  )')
    # placement: one image per component, pins already rotated, place at rot 0
    A('  (placement')
    padstacks = {}
    images = []
    netpins = {}
    for p in PARTS:
        pads = [pd for pd in pad_list(p) if pd['type'] != 'np_thru_hole' and
                any(l in ('F.Cu', 'B.Cu', '*.Cu') for l in pd['layers'])]
        if not pads: continue
        A(f'    (component "IMG_{p["ref"]}" (place "{p["ref"]}" {um(p["x"])} {um(-p["y"])} front 0))')
        seen = {}
        pins = []
        for pd in pads:
            num = pd['num'] or 'X'
            k = seen.get(num, 0); seen[num] = k + 1
            pname = num if k == 0 else f'{num}@{k}'
            ps = padstack_name(pd)
            padstacks.setdefault(ps, padstack_def(ps, pd))
            pins.append(f'      (pin "{ps}" "{pname}" {um(pd["x"] - p["x"])} {um(-(pd["y"] - p["y"]))})')
            if pd['net']:
                netpins.setdefault(pd['net'], []).append(f'{p["ref"]}-{pname}')
        images.append(f'    (image "IMG_{p["ref"]}"\n' + '\n'.join(pins) + '\n    )')
    A('  )')
    A('  (library')
    lines += images
    lines += list(padstacks.values())
    for s, d in vias:
        n = via_name(s, d)
        A(f'    (padstack "{n}"\n      (shape (circle F.Cu {um(s)}))\n      (shape (circle B.Cu {um(s)}))\n      (attach off)\n    )')
    A('  )')
    A('  (network')
    for n, pins in netpins.items():
        if n in SKIP_NETS: continue
        A(f'    (net "{n}"\n      (pins ' + ' '.join(pins) + '))')
    route_classes = route_classes or {}
    assigned = set()
    for cname, c in NETCLASS.items():
        if cname == 'Default': continue
        members = [n for n in c['nets'] if n in netpins and n not in SKIP_NETS]
        assigned |= set(members)
        w, cl = route_classes.get(cname, (c['width'], c['clearance']))
        A(f'    (class "{cname}" ' + ' '.join(f'"{n}"' for n in members) +
          f'\n      (circuit (use_via "{via_name(*c["via"])}"))\n      (rule (width {um(w)}) (clearance {um(cl)})))')
    rest = [n for n in netpins if n not in assigned and n not in SKIP_NETS]
    c = NETCLASS['Default']
    A('    (class "kicad_default" ' + ' '.join(f'"{n}"' for n in rest) +
      f'\n      (circuit (use_via "{via_name(*c["via"])}"))\n      (rule (width {um(c["width"])}) (clearance {um(c["clearance"])})))')
    A('  )')
    A('  (wiring')
    for net, layer, w, poly in power_routes.TRACKS:
        pts = ' '.join(f'{um(x)} {um(-y)}' for x, y in poly)
        A(f'    (wire (path {layer} {um(w)} {pts}) (net "{net}") (type protect))')
    for net, x, y, s, dd in power_routes.all_vias():
        A(f'    (via "{via_name(s, dd)}" {um(x)} {um(-y)} (net "{net}") (type protect))')
    A('  )')
    A(')')
    open(path, 'w').write('\n'.join(lines) + '\n')
    return netpins

def tokenize(s):
    return re.findall(r'\(|\)|"[^"]*"|[^\s()]+', s)

def parse(tokens):
    stack = [[]]
    for t in tokens:
        if t == '(':
            stack.append([])
        elif t == ')':
            x = stack.pop(); stack[-1].append(x)
        else:
            stack[-1].append(t.strip('"'))
    return stack[0][0]

def find(node, key):
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            yield c

def read_ses(path):
    tree = parse(tokenize(open(path).read()))
    routes = next(find(tree, 'routes'))
    res = next(find(routes, 'resolution'))
    scale = {'um': 1e-3, 'mm': 1.0, 'mil': 0.0254}[res[1]] / float(res[2])
    vianames = {}
    lib = list(find(routes, 'library_out'))
    if lib:
        for ps in find(lib[0], 'padstack'):
            sh = next(find(ps, 'shape'))[1]
            vianames[ps[1]] = float(sh[2]) * scale
    tracks, vias = [], []
    nout = next(find(routes, 'network_out'))
    for net in find(nout, 'net'):
        name = net[1]
        for wire in find(net, 'wire'):
            if any(isinstance(c, list) and c[0] == 'type' and c[1] == 'protect' for c in wire):
                continue
            pth = next(find(wire, 'path'))
            layer, w = pth[1], float(pth[2]) * scale
            co = [float(v) * scale for v in pth[3:]]
            pts = [(co[i], -co[i + 1]) for i in range(0, len(co), 2)]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                tracks.append([name, layer, round(w, 4), round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)])
        for v in find(net, 'via'):
            if any(isinstance(c, list) and c[0] == 'type' and c[1] == 'protect' for c in v):
                continue
            pname = v[1]; x = float(v[2]) * scale; y = -float(v[3]) * scale
            m = re.search(r'_([\d.]+):([\d.]+)_um', pname)
            s, d = (float(m.group(1)) / 1000, float(m.group(2)) / 1000) if m else (vianames.get(pname, 0.6), 0.3)
            vias.append([name, round(x, 4), round(y, 4), s, d])
    return dict(tracks=tracks, vias=vias)
