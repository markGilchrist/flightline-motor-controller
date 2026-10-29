"""Re-derive the netlist from schematic geometry (pins, wires, labels, GND symbols) and compare to design.py."""
from gen_sch import build
from design import PARTS
sch, d = build()
pts = {}
parent = {}
def f(a):
    while parent.setdefault(a, a) != a: a = parent[a]
    return a
def u(a, b): parent[f(a)] = f(b)
R = lambda x, y: (round(x, 3), round(y, 3))
# wires: endpoints connect; check no endpoint lies mid-segment of another wire or on a pin it doesn't end at
wires = [(R(a, b), R(c, e)) for a, b, c, e in d['wires']]
for a, b in wires: u(('pt',) + a, ('pt',) + b)
for ref, num, x, y in d['pins']: u(('pin', ref, num), ('pt',) + R(x, y))
for net, x, y, ang in d['labels']: u(('net', net), ('pt',) + R(x, y))
for x, y in d['gnds']: u(('net', 'GND'), ('pt',) + R(x, y))
def on_seg(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if (x, y) in (a, b): return False
    cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    return abs(cross) < 1e-6 and min(x1, x2) - 1e-6 <= x <= max(x1, x2) + 1e-6 and min(y1, y2) - 1e-6 <= y <= max(y1, y2) + 1e-6
allpts = {R(x, y) for _, _, x, y in d['pins']} | {p for w in wires for p in w}
mid = [(p, w) for p in allpts for w in wires if on_seg(p, *w)]
print('T-junctions / mid-wire touches:', mid[:5], len(mid))
bad = 0
for p in PARTS:
    for num, net in p['pins'].items():
        if net is None: continue
        if f(('pin', p['ref'], num)) != f(('net', net)):
            print('MISMATCH', p['ref'], num, net); bad += 1
nets = {}
for p in PARTS:
    for num, net in p['pins'].items():
        if net: nets.setdefault(f(('net', net)), set()).add(net)
merged = [v for v in nets.values() if len(v) > 1]
flag_bad = [(net, x, y) for net, x, y in d.get('flags', []) if f(('pt',) + R(x, y)) != f(('net', net))]
print('pins checked, mismatches:', bad, ' merged nets:', merged)
print('PWR_FLAGs:', [n for n, _, _ in d.get('flags', [])], ' misplaced:', flag_bad)
