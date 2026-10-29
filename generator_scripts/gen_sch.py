"""Generate a KiCad schematic (.kicad_sch, KiCad 7 file format so KiCad 7, 8 and 9 all open it) and a PDF from design.py.
Style: every symbol is drawn upright, each pin gets a short wire stub ending in a net label
(GND uses a power symbol). Labels with the same name are connected, so the schematic's
netlist is exactly design.py's netlist."""
import uuid, math
from design import PARTS, sym_uuid

# deterministic UUIDs: regenerating the schematic gives the same file unless the design changes
_uuid_n = [0]
def U():
    _uuid_n[0] += 1
    return str(uuid.uuid5(uuid.UUID('9d0f5c3e-2f7a-4c1b-8e4d-1a2b3c4d5e6f'), str(_uuid_n[0])))
LIB = 'motor_ctrl'
G = 2.54

# ---------------------------------------------------------------- symbol library
# graphics in symbol coords (mm, y up). pins: (number, name, x, y, angle, length, etype)
def two_pin_vertical(body, top_len=2.54):
    return [('1', '~', 0, 5.08, 270, top_len, 'passive'), ('2', '~', 0, -5.08, 90, top_len, 'passive')]

def arcs_inductor():
    g = []
    for i in range(4):
        y0 = 2.54 - i * 1.27
        g.append(('arc', (0, y0), (0.635, y0 - 0.635), (0, y0 - 1.27)))
    return g

def diode_body(kind):
    g = [('poly', [(-1.27, -1.27), (1.27, -1.27), (0, 1.016), (-1.27, -1.27)], True)]
    if kind == 'zener':
        g.append(('poly', [(-1.778, 1.524), (-1.27, 1.016), (1.27, 1.016), (1.778, 0.508)], False))
    elif kind == 'schottky':
        g.append(('poly', [(-1.778, 0.508), (-1.778, 1.016), (1.27, 1.016), (1.27, 1.524), (1.778, 1.524)], False))
    else:
        g.append(('poly', [(-1.27, 1.016), (1.27, 1.016)], False))
    if kind == 'led':
        for dy in (0.0, -1.0):
            g.append(('poly', [(1.8, 0.4 + dy), (3.0, 1.2 + dy)], False))
            g.append(('poly', [(2.4, 1.2 + dy), (3.0, 1.2 + dy), (2.8, 0.6 + dy)], False))
    g.append(('poly', [(0, 2.54), (0, 1.016)], False))
    g.append(('poly', [(0, -2.54), (0, -1.27)], False))
    return g

def mosfet(p):
    g = [('poly', [(-2.54, 0), (-1.016, 0)], False),
         ('poly', [(-1.016, -1.905), (-1.016, 1.905)], False),
         ('poly', [(-0.508, 1.905), (-0.508, 1.016)], False),
         ('poly', [(-0.508, 0.508), (-0.508, -0.508)], False),
         ('poly', [(-0.508, -1.016), (-0.508, -1.905)], False),
         ('poly', [(-0.508, 1.524), (2.54, 1.524), (2.54, 2.54)], False),
         ('poly', [(-0.508, -1.524), (2.54, -1.524), (2.54, -2.54)], False),
         ('poly', [(-0.508, 0), (2.54, 0), (2.54, -1.524)], False),
         ('circle', (0.8, 0), 3.0)]
    if p:   # arrow pointing out of channel
        g.append(('poly', [(0.254, 0), (1.27, 0.508), (1.27, -0.508), (0.254, 0)], True))
    else:
        g.append(('poly', [(-0.508, 0), (0.508, 0.508), (0.508, -0.508), (-0.508, 0)], True))
    pins = [('1', 'G', -5.08, 0, 0, 2.54, 'input'), ('2', 'D', 2.54, 5.08, 270, 2.54, 'passive'),
            ('3', 'S', 2.54, -5.08, 90, 2.54, 'passive')]
    return g, pins

def ic_box(left, right, width=15.24, name_vis=True):
    """left/right: lists of (num, name, etype) or None for a gap."""
    n = max(len(left), len(right))
    h = (n + 1) * G
    top = h / 2
    top = math.ceil(top / G) * G
    pins = []
    for side, lst in ((-1, left), (1, right)):
        for i, pn in enumerate(lst):
            if pn is None: continue
            num, name, et = pn
            y = top - (i + 1) * G
            x = side * (width / 2 + G)
            pins.append((num, name, x, y, 0 if side < 0 else 180, G, et))
    bottom = top - (n + 1) * G
    return [('rect', (-width / 2, top), (width / 2, bottom))], pins

SYMS = {}
def defsym(kind, graphics, pins, ref, show_pin_names=False, show_pin_numbers=True, power=False):
    SYMS[kind] = dict(g=graphics, pins=pins, ref=ref, pn=show_pin_names, pnum=show_pin_numbers, power=power)

defsym('r', [('rect', (-1.016, 2.54), (1.016, -2.54))], two_pin_vertical(None), 'R', show_pin_numbers=False)
defsym('c', [('poly', [(-2.032, 0.635), (2.032, 0.635)], False), ('poly', [(-2.032, -0.635), (2.032, -0.635)], False),
             ('poly', [(0, 2.54), (0, 0.635)], False), ('poly', [(0, -2.54), (0, -0.635)], False)],
       two_pin_vertical(None), 'C', show_pin_numbers=False)
defsym('cp', [('rect', (-2.286, 0.889), (2.286, 0.381)), ('rect', (-2.286, -0.381), (2.286, -0.889), True),
              ('poly', [(-1.778, 2.286), (-0.762, 2.286)], False), ('poly', [(-1.27, 2.794), (-1.27, 1.778)], False),
              ('poly', [(0, 2.54), (0, 0.889)], False), ('poly', [(0, -2.54), (0, -0.889)], False)],
       two_pin_vertical(None), 'C', show_pin_numbers=False)
defsym('l', arcs_inductor() + [('poly', [(0, 2.54), (0, 2.54)], False)], two_pin_vertical(None), 'L', show_pin_numbers=False)
for k in ('schottky', 'zener', 'led'):
    defsym(k, diode_body(k), [('1', 'K', 0, 5.08, 270, 2.54, 'passive'), ('2', 'A', 0, -5.08, 90, 2.54, 'passive')], 'D')
defsym('tvs', [('poly', [(-1.27, 0), (1.27, 0), (0, 1.778), (-1.27, 0)], False),
               ('poly', [(-1.27, 0), (1.27, 0), (0, -1.778), (-1.27, 0)], False),
               ('poly', [(-1.778, 2.286), (-1.27, 1.778), (1.27, 1.778), (1.778, 1.27)], False),
               ('poly', [(-1.778, -1.27), (-1.27, -1.778), (1.27, -1.778), (1.778, -2.286)], False),
               ('poly', [(0, 2.54), (0, 1.778)], False), ('poly', [(0, -2.54), (0, -1.778)], False)],
       [('1', 'A1', 0, 5.08, 270, 2.54, 'passive'), ('2', 'A2', 0, -5.08, 90, 2.54, 'passive')], 'D')
defsym('fuse', [('rect', (-0.762, 2.54), (0.762, -2.54)), ('poly', [(0, 2.54), (0, -2.54)], False)],
       two_pin_vertical(None), 'F', show_pin_numbers=False)
defsym('sw', [('circle', (0, 1.27), 0.4), ('circle', (0, -1.27), 0.4), ('poly', [(0.4, -1.27), (1.6, 1.6)], False),
              ('poly', [(0, 2.54), (0, 1.67)], False), ('poly', [(0, -2.54), (0, -1.67)], False),
              ('poly', [(1.0, 0.2), (2.4, 0.2)], False), ('poly', [(2.4, 1.2), (2.4, -0.8)], False)],
       two_pin_vertical(None), 'SW', show_pin_numbers=False)
g, pn = mosfet(False); defsym('nmos', g, pn, 'Q', show_pin_names=False)
g, pn = mosfet(True); defsym('pmos', g, pn, 'Q', show_pin_names=False)
defsym('dual_schottky',
       [('poly', [(-2.54, -1.27), (-0.508, -1.27), (-1.524, 0.762), (-2.54, -1.27)], True),
        ('poly', [(0.508, -1.27), (2.54, -1.27), (1.524, 0.762), (0.508, -1.27)], True),
        ('poly', [(-2.794, 0.762), (-0.254, 0.762)], False), ('poly', [(0.254, 0.762), (2.794, 0.762)], False),
        ('poly', [(-1.524, 0.762), (-1.524, 2.54), (1.524, 2.54), (1.524, 0.762)], False),
        ('poly', [(0, 2.54), (0, 2.54)], False),
        ('poly', [(-1.524, -1.27), (-1.524, -2.54)], False), ('poly', [(1.524, -1.27), (1.524, -2.54)], False),
        ('poly', [(-1.524, -2.54), (-2.54, -2.54)], False), ('poly', [(1.524, -2.54), (2.54, -2.54)], False)],
       [('2', 'K', 0, 5.08, 270, 2.54, 'passive'), ('1', 'A1', -5.08, -2.54, 0, 2.54, 'passive'),
        ('3', 'A2', 5.08, -2.54, 180, 2.54, 'passive')], 'D', show_pin_names=False)
defsym('conn2', [('rect', (-2.54, 1.27), (1.27, -3.81))],
       [('1', 'Pin_1', 3.81, 0, 180, 2.54, 'passive'), ('2', 'Pin_2', 3.81, -2.54, 180, 2.54, 'passive')], 'J',
       show_pin_names=False)
defsym('conn4', [('rect', (-2.54, 1.27), (1.27, -8.89))],
       [(str(i + 1), f'Pin_{i + 1}', 3.81, -i * G, 180, 2.54, 'passive') for i in range(4)], 'J', show_pin_names=False)
g, pn = ic_box([('2', 'VIN', 'power_in'), ('3', 'EN', 'input'), ('4', 'PG', 'open_collector'), None,
                ('1', 'PGND', 'power_in'), ('9', 'EP', 'passive')],
               [('8', 'SW', 'power_out'), ('7', 'BOOT', 'passive'), ('6', 'VCC', 'power_out'), ('5', 'FB', 'input')], 12.7)
defsym('buck', g, pn, 'U', show_pin_names=True)
g, pn = ic_box([('3', 'IN+', 'input'), ('4', 'IN-', 'input'), ('1', 'VDD', 'power_in')],
               [('5', 'OUT', 'output'), None, ('2', 'GND', 'power_in')], 10.16)
defsym('driver', g, pn, 'U', show_pin_names=True)
g, pn = ic_box([('1', 'I/O1', 'passive'), ('3', 'I/O2', 'passive'), ('2', 'GND', 'passive')],
               [('6', 'I/O1', 'passive'), ('4', 'I/O2', 'passive'), ('5', 'VBUS', 'passive')], 10.16)
defsym('esd', g, pn, 'U', show_pin_names=True)
g, pn = ic_box([], [('A4', 'VBUS', 'passive'), ('A9', 'VBUS', 'passive'), ('B4', 'VBUS', 'passive'), ('B9', 'VBUS', 'passive'),
                    ('A5', 'CC1', 'bidirectional'), ('B5', 'CC2', 'bidirectional'),
                    ('A6', 'D+', 'bidirectional'), ('B6', 'D+', 'bidirectional'),
                    ('A7', 'D-', 'bidirectional'), ('B7', 'D-', 'bidirectional'),
                    ('A8', 'SBU1', 'bidirectional'), ('B8', 'SBU2', 'bidirectional'),
                    ('A1', 'GND', 'passive'), ('A12', 'GND', 'passive'), ('B1', 'GND', 'passive'), ('B12', 'GND', 'passive'),
                    ('S1', 'SHIELD', 'passive')], 12.7)
defsym('usbc', g, pn, 'J', show_pin_names=True)
ESP_L = [('2', '3V3', 'power_in'), ('3', 'EN', 'input'), ('27', 'IO0', 'bidirectional'), ('4', 'IO4', 'bidirectional'),
         ('5', 'IO5', 'bidirectional'), ('6', 'IO6', 'bidirectional'), ('7', 'IO7', 'bidirectional'),
         ('8', 'IO15', 'bidirectional'), ('9', 'IO16', 'bidirectional'), ('10', 'IO17', 'bidirectional'),
         ('11', 'IO18', 'bidirectional'), ('12', 'IO8', 'bidirectional'), ('15', 'IO3', 'bidirectional'),
         ('16', 'IO46', 'bidirectional'), ('17', 'IO9', 'bidirectional'), ('18', 'IO10', 'bidirectional'),
         ('19', 'IO11', 'bidirectional'), ('20', 'IO12', 'bidirectional'), ('21', 'IO13', 'bidirectional'),
         None, ('1', 'GND', 'power_in'), ('40', 'GND', 'power_in'), ('41', 'GND(EP)', 'power_in')]
ESP_R = [('13', 'IO19/USB_D-', 'bidirectional'), ('14', 'IO20/USB_D+', 'bidirectional'), ('39', 'IO1', 'bidirectional'),
         ('38', 'IO2', 'bidirectional'), ('22', 'IO14', 'bidirectional'), ('23', 'IO21', 'bidirectional'),
         ('24', 'IO47', 'bidirectional'), ('25', 'IO48', 'bidirectional'), ('26', 'IO45', 'bidirectional'),
         ('28', 'IO35', 'bidirectional'), ('29', 'IO36', 'bidirectional'), ('30', 'IO37', 'bidirectional'),
         ('31', 'IO38', 'bidirectional'), ('32', 'IO39', 'bidirectional'), ('33', 'IO40', 'bidirectional'),
         ('34', 'IO41', 'bidirectional'), ('35', 'IO42', 'bidirectional'), ('36', 'RXD0', 'bidirectional'),
         ('37', 'TXD0', 'bidirectional')]
g, pn = ic_box(ESP_L, ESP_R, 22.86)
defsym('esp32', g, pn, 'U', show_pin_names=True)
defsym('hole', [('circle', (0, 0), 1.6)], [], 'H')
defsym('GND', [('poly', [(0, 0), (0, -1.27), (1.27, -1.27), (0, -2.54), (-1.27, -1.27), (0, -1.27)], False)],
       [('1', 'GND', 0, 0, 270, 0, 'power_in')], '#PWR', power=True)
# ERC marker: tells KiCad a net is powered when its source is a passive part (diode, resistor, inductor, connector)
defsym('PWR_FLAG', [('poly', [(0, 0), (0, 1.27), (-1.016, 1.905), (0, 2.54), (1.016, 1.905), (0, 1.27)], False)],
       [('1', 'pwr', 0, 0, 90, 0, 'power_out')], '#FLG', power=True)

# nets whose only sources are passive pins; each gets a PWR_FLAG above the block frames
PWR_FLAGS = [('GND', 25.4), ('VIN_BUCK', 40.64), ('+3V3', 55.88), ('VDRV', 71.12)]
PWR_FLAG_Y = 19.05

# ---------------------------------------------------------------- placement on an A3 sheet (mm, y down)
PLACE = {
    # power input / protection
    'J1': (25.4, 50.8), 'F1': (45.72, 45.72), 'D1': (63.5, 50.8), 'Q1': (81.28, 43.18), 'R1': (78.74, 60.96),
    'D2': (99.06, 50.8), 'C1': (111.76, 50.8), 'C2': (124.46, 50.8), 'C3': (137.16, 50.8), 'C4': (149.86, 50.8),
    # motor stage
    'R4': (190.5, 50.8), 'D4': (203.2, 50.8), 'C5': (215.9, 50.8), 'C6': (228.6, 50.8),
    'U2': (205.74, 78.74), 'R5': (180.34, 91.44), 'R2': (236.22, 73.66), 'R3': (248.92, 91.44),
    'Q2': (269.24, 78.74), 'D3': (281.94, 55.88), 'J2': (302.26, 55.88),
    # 3.3 V buck
    'D5': (25.4, 127.0), 'D6': (38.1, 127.0), 'C7': (50.8, 127.0), 'C8': (63.5, 127.0), 'C9': (76.2, 127.0),
    'R6': (88.9, 127.0), 'U1': (119.38, 132.08), 'C11': (101.6, 157.48), 'C10': (149.86, 121.92), 'L1': (162.56, 121.92),
    'R7': (177.8, 127.0), 'R8': (177.8, 147.32), 'C12': (190.5, 127.0), 'C13': (203.2, 127.0),
    # ESP32
    'U3': (299.72, 160.02), 'C14': (233.68, 137.16), 'C15': (246.38, 137.16), 'R9': (233.68, 172.72),
    'C16': (246.38, 172.72), 'SW1': (259.08, 172.72), 'R10': (233.68, 203.2), 'SW2': (246.38, 203.2),
    'R13': (365.76, 132.08), 'R14': (365.76, 154.94), 'C17': (378.46, 154.94),
    'R15': (391.16, 132.08), 'D7': (391.16, 154.94), 'J4': (365.76, 180.34),
    'R16': (391.16, 187.96), 'D8': (391.16, 210.82),     # 3V3 power LED
    # wiper park input
    'J5': (177.8, 200.66), 'R17': (195.58, 195.58), 'R18': (205.74, 195.58), 'R19': (205.74, 220.98),
    'C18': (215.9, 220.98),
    # USB
    'J3': (40.64, 210.82), 'R11': (91.44, 236.22), 'R12': (104.14, 236.22), 'U4': (134.62, 205.74),
    # holes
    'H1': (360.68, 254.0), 'H2': (373.38, 254.0), 'H3': (386.08, 254.0), 'H4': (398.78, 254.0),
}
BLOCKS = [  # title, x0, y0, x1, y1
    ('POWER INPUT, FUSE, LOAD-DUMP TVS, REVERSE-POLARITY PROTECTION', 12.7, 27.94, 165.1, 76.2),
    ('MOTOR SWITCH: GATE DRIVER + LOW-SIDE N-MOSFET + FREEWHEEL DIODE', 172.72, 27.94, 320.04, 104.14),
    ('3.3 V BUCK (12 V or USB)', 12.7, 106.68, 218.44, 172.72),
    ('ESP32-S3 MODULE, RESET/BOOT, BATTERY SENSE, LEDS, AUX', 223.52, 116.84, 406.4, 228.6),
    ('USB-C (PROGRAMMING / DEBUG)', 12.7, 182.88, 162.56, 254.0),
    ('WIPER PARK SWITCH INPUT', 167.64, 177.8, 222.25, 234.95),
]
NOTES = [
    'Motor: J2 pin 2 = +12 V (always on), pin 1 = MOTOR- (switched to GND by Q2).',
    'PWM from ESP32 GPIO4, 20 kHz. R5 holds the gate driver input low while the ESP32 boots.',
    'Battery sense: VSENSE = VBAT x 18k / 118k  ->  14.4 V reads 2.20 V on GPIO1.',
    'Q1 + D2: reverse-battery protection (P-MOSFET, gate clamped to 12 V).',
    'D1 SMCJ20CA clamps load-dump spikes; everything on the 12 V side is rated >= 35 V.',
    'Rated for motors up to 10 A continuous (15 A fuse). Use 2 oz copper.',
    'J5 park input: IO7 reads PARK / 11. Firmware compares it with the battery voltage (works for contact-to-GND and 31b park switches).',
]

def sym_name(kind): return f'{LIB}:{kind}'

def fmt(v): return f'{v:.4f}'.rstrip('0').rstrip('.') if abs(v) > 1e-9 else '0'

def eff(size=1.27, hide=False, justify=None):
    j = f' (justify {justify})' if justify else ''
    return f'(effects (font (size {size} {size})){j}{" hide" if hide else ""})'

def lib_symbol_sexpr(kind):
    s = SYMS[kind]
    name = sym_name(kind)
    short = kind
    out = [f'(symbol "{name}"']
    if s['power']: out.append('(power)')
    if not s['pnum']: out.append('(pin_numbers hide)')
    out.append('(pin_names (offset 0.254)' + ('' if s['pn'] else ' hide') + ')')
    out.append('(in_bom yes) (on_board yes)')
    out.append(f'(property "Reference" "{s["ref"]}" (id 0) (at 0 0 0) {eff()})')
    out.append(f'(property "Value" "{kind}" (id 1) (at 0 0 0) {eff()})')
    out.append(f'(property "Footprint" "" (id 2) (at 0 0 0) {eff(hide=True)})')
    out.append(f'(property "Datasheet" "" (id 3) (at 0 0 0) {eff(hide=True)})')
    out.append(f'(symbol "{short}_0_1"')
    for g in s['g']:
        out.append(graphic_sexpr(g))
    out.append(')')
    out.append(f'(symbol "{short}_1_1"')
    for num, nm, x, y, ang, ln, et in s['pins']:
        hide = ' hide' if s['power'] else ''
        out.append(f'(pin {et} line (at {fmt(x)} {fmt(y)} {ang}) (length {fmt(ln)}){hide} '
                   f'(name "{nm}" {eff()}) (number "{num}" {eff()}))')
    out.append(')')
    out.append(')')
    return '\n'.join(out)

def graphic_sexpr(g):
    st = '(stroke (width 0.254) (type default))'
    if g[0] == 'rect':
        fill = 'outline' if len(g) > 3 and g[3] else 'background'
        return f'(rectangle (start {fmt(g[1][0])} {fmt(g[1][1])}) (end {fmt(g[2][0])} {fmt(g[2][1])}) {st} (fill (type {fill})))'
    if g[0] == 'poly':
        pts = ' '.join(f'(xy {fmt(x)} {fmt(y)})' for x, y in g[1])
        return f'(polyline (pts {pts}) {st} (fill (type {"outline" if g[2] else "none"})))'
    if g[0] == 'circle':
        return f'(circle (center {fmt(g[1][0])} {fmt(g[1][1])}) (radius {fmt(g[2])}) {st} (fill (type none)))'
    if g[0] == 'arc':
        return (f'(arc (start {fmt(g[1][0])} {fmt(g[1][1])}) (mid {fmt(g[2][0])} {fmt(g[2][1])}) '
                f'(end {fmt(g[3][0])} {fmt(g[3][1])}) {st} (fill (type none)))')
    raise ValueError(g)

def pin_end(X, Y, pin, rot=0):
    """sheet coords of a pin's connection point for a symbol at (X, Y), rotation 0 or 180."""
    k = -1 if rot == 180 else 1
    return X + k * pin[2], Y - k * pin[3]

def stub_dir(pin, rot=0):
    # direction from connection point away from the body (sheet coords, y down)
    ang = pin[4]
    d = {0: (-1, 0), 180: (1, 0), 270: (0, -1), 90: (0, 1)}[ang]
    return (-d[0], -d[1]) if rot == 180 else d

def part_rot(p):
    s = SYMS[p['kind']]
    if p['kind'] in ('r', 'c', 'cp', 'l', 'tvs', 'fuse', 'sw', 'schottky', 'zener', 'led'):
        top = [pp for pp in s['pins'] if pp[4] == 270]
        if top and p['pins'].get(top[0][0]) == 'GND':
            return 180
    return 0

def build():
    _uuid_n[0] = 0
    root = U()
    items = []        # sexpr strings
    draw = dict(symbols=[], wires=[], labels=[], gnds=[], nc=[], texts=[], blocks=BLOCKS)
    pwr_n = [0]
    used_kinds = set(['GND'])

    def place_gnd(x, y):
        pwr_n[0] += 1
        ref = f'#PWR{pwr_n[0]:02d}'
        items.append(f'''(symbol (lib_id "{sym_name('GND')}") (at {fmt(x)} {fmt(y)} 0) (unit 1)
  (in_bom yes) (on_board yes) (dnp no) (uuid "{U()}")
  (property "Reference" "{ref}" (id 0) (at {fmt(x)} {fmt(y + 6.35)} 0) {eff(hide=True)})
  (property "Value" "GND" (id 1) (at {fmt(x)} {fmt(y + 4.2)} 0) {eff()})
  (property "Footprint" "" (id 2) (at {fmt(x)} {fmt(y)} 0) {eff(hide=True)})
  (property "Datasheet" "" (id 3) (at {fmt(x)} {fmt(y)} 0) {eff(hide=True)})
  (pin "1" (uuid "{U()}"))
  (instances (project "motor_ctrl" (path "/{root}" (reference "{ref}") (unit 1)))))''')
        draw['gnds'].append((x, y))

    pending = []      # net labels, emitted after all parts are placed
    for p in PARTS:
        kind = p['kind']
        used_kinds.add(kind)
        X, Y = PLACE[p['ref']]
        s = SYMS[kind]
        rot = part_rot(p)
        # reference/value text positions: to the right of the body
        xs = [pp[2] for pp in s['pins']] or [0]
        right = max(xs + [2.54]) + 1.27
        top = max([pp[3] for pp in s['pins']] + [2.54])
        if kind in ('esp32', 'buck', 'driver', 'esd', 'usbc'):
            rx, ry, vx, vy, just = X, Y - top - 2.54, X, Y - top - 0.6, None
            rx, ry = X - 0, Y - top - 4.2
        elif kind == 'hole':
            rx, ry, vx, vy, just = X + 2.5, Y - 0.8, X + 2.5, Y + 1.2, 'left'
        else:
            rx, ry, vx, vy, just = X + 2.2, Y - 0.8, X + 2.2, Y + 1.2, 'left'
        if kind in ('nmos', 'pmos'):
            rx, ry, vx, vy = X + 5.5, Y - 0.8, X + 5.5, Y + 1.2
        if kind == 'dual_schottky':
            rx, ry, vx, vy, just = X - 2.54, Y + 5.5, X - 2.54, Y + 7.5, 'left'
        if kind in ('conn2', 'conn4'):
            rx, ry, vx, vy, just = X - 1.27, Y - 3.0, X - 1.27, Y + (6.0 if kind == 'conn2' else 11.0), None
        if kind in ('esp32', 'buck', 'driver', 'esd', 'usbc'):
            vx, vy = X, Y + (len(s['pins']) and (min(pp[3] for pp in s['pins']) * -1 + 4.2))
        fang = 0
        if kind in ('r', 'c', 'cp', 'l', 'tvs', 'fuse', 'zener', 'schottky', 'led', 'sw'):
            # rows of vertical two-pin parts are 12.7 mm apart: write ref and value vertically beside the
            # body, otherwise values like "470uF 35V" run into the next column
            off = 4.3 if kind == 'sw' else 3.0
            rx, ry, vx, vy, just, fang = X + off, Y, X + off + 1.9, Y, None, 90
        props = [('Reference', p['ref'], rx, ry, False, fang), ('Value', p['value'], vx, vy, False, fang),
                 ('Footprint', p['fp'], X, Y, True, 0), ('Datasheet', '', X, Y, True, 0),
                 ('MPN', p.get('mpn', ''), X, Y, True, 0), ('Note', p.get('note', ''), X, Y, True, 0)]
        ptxt = '\n'.join(f'  (property "{k}" "{v}" (id {i}) (at {fmt(x)} {fmt(y)} {a}) {eff(hide=h, justify=just if k in ("Reference", "Value") else None)})'
                         for i, (k, v, x, y, h, a) in enumerate(props))
        pins_txt = '\n'.join(f'  (pin "{pp[0]}" (uuid "{U()}"))' for pp in s['pins'])
        items.append(f'''(symbol (lib_id "{sym_name(kind)}") (at {fmt(X)} {fmt(Y)} {rot}) (unit 1)
  (in_bom {"no" if kind == "hole" else "yes"}) (on_board yes) (dnp no) (uuid "{sym_uuid(p['ref'])}")
{ptxt}
{pins_txt}
  (instances (project "motor_ctrl" (path "/{root}" (reference "{p['ref']}") (unit 1)))))''')
        draw['symbols'].append(dict(kind=kind, X=X, Y=Y, rot=rot, ref=(p['ref'], rx, ry, just), val=(p['value'], vx, vy, just)))

        # stubs + labels / GND symbols / no-connects
        for pin in s['pins']:
            num = pin[0]
            net = p['pins'].get(num)
            px, py = pin_end(X, Y, pin, rot)
            dx, dy = stub_dir(pin, rot)
            draw.setdefault('pins', []).append((p['ref'], pin[0], round(px, 3), round(py, 3)))
            if net is None:
                items.append(f'(no_connect (at {fmt(px)} {fmt(py)}) (uuid "{U()}"))')
                draw['nc'].append((px, py))
                continue
            L = 2.54
            chained = False
            if net == 'GND' and dx != 0:
                def below(q):
                    b = [r for r in s['pins'] if r[4] == q[4] and abs(r[2] - q[2]) < 1e-6 and abs(r[3] - (q[3] - G)) < 1e-6]
                    return b[0] if b else None
                # a run of adjacent GND pins shares one GND symbol under its lowest pin; the others drop onto
                # the stub end of the pin below
                chained = below(pin) is not None and p['pins'].get(below(pin)[0]) == 'GND'
                last = pin
                while below(last) is not None and p['pins'].get(below(last)[0]) == 'GND':
                    last = below(last)
                # if the pin under the run belongs to another net, step further out so the drop to the
                # GND symbol cannot land on that pin's stub end
                if below(last) is not None and p['pins'].get(below(last)[0]) is not None:
                    L = 5.08
            ex, ey = px + dx * L, py + dy * L
            if net == 'GND':
                # route the stub downward to a GND symbol
                if dy == -1:   # pin points up: stub up then GND symbol would be upside down; use label instead
                    pass
                else:
                    if dx != 0:
                        items.append(wire(px, py, ex, ey)); draw['wires'].append((px, py, ex, ey))
                        items.append(wire(ex, ey, ex, ey + G)); draw['wires'].append((ex, ey, ex, ey + G))
                        if chained:
                            items.append(f'(junction (at {fmt(ex)} {fmt(ey + G)}) (diameter 0) (color 0 0 0 0) (uuid "{U()}"))')
                        else:
                            place_gnd(ex, ey + G)
                    else:
                        items.append(wire(px, py, ex, ey)); draw['wires'].append((px, py, ex, ey))
                        place_gnd(ex, ey)
                    continue
            items.append(wire(px, py, ex, ey)); draw['wires'].append((px, py, ex, ey))
            if dx == -1: ang, j = 180, 'right bottom'
            elif dx == 1: ang, j = 0, 'left bottom'
            elif dy == -1: ang, j = 90, 'left bottom'
            else: ang, j = 270, 'right bottom'
            pending.append((net, ex, ey, ang, j))

    # Stacked parts joined by one net (R7/R8, R13/R14, ...) would get two labels on top of each other:
    # join them with a wire and keep only the lower label.
    def emit_label(net, x, y, ang, j):
        items.append(f'(label "{net}" (at {fmt(x)} {fmt(y)} {ang}) (fields_autoplaced) '
                     f'(effects (font (size 1.27 1.27)) (justify {j})) (uuid "{U()}"))')
        draw['labels'].append((net, x, y, ang))
    skip = set()
    for i, (n1, x1, y1, a1, _) in enumerate(pending):
        for k, (n2, x2, y2, a2, _) in enumerate(pending):
            if n1 == n2 and a1 == 270 and a2 == 90 and abs(x1 - x2) < 1e-6 and 0 < y2 - y1 <= 12.7:
                items.append(wire(x1, y1, x2, y2)); draw['wires'].append((x1, y1, x2, y2))
                skip.add(i)
    for i, lab in enumerate(pending):
        if i not in skip:
            emit_label(*lab)

    # power flags: flag symbol, short wire down, then a GND symbol or a net label
    nflg = 0
    for net, fx in PWR_FLAGS:
        nflg += 1
        ref = f'#FLG{nflg:02d}'
        used_kinds.add('PWR_FLAG')
        items.append(f'''(symbol (lib_id "{sym_name('PWR_FLAG')}") (at {fmt(fx)} {fmt(PWR_FLAG_Y)} 0) (unit 1)
  (in_bom yes) (on_board yes) (dnp no) (uuid "{U()}")
  (property "Reference" "{ref}" (id 0) (at {fmt(fx)} {fmt(PWR_FLAG_Y - 1.9)} 0) {eff(hide=True)})
  (property "Value" "PWR_FLAG" (id 1) (at {fmt(fx)} {fmt(PWR_FLAG_Y - 3.6)} 0) {eff()})
  (property "Footprint" "" (id 2) (at {fmt(fx)} {fmt(PWR_FLAG_Y)} 0) {eff(hide=True)})
  (property "Datasheet" "" (id 3) (at {fmt(fx)} {fmt(PWR_FLAG_Y)} 0) {eff(hide=True)})
  (pin "1" (uuid "{U()}"))
  (instances (project "motor_ctrl" (path "/{root}" (reference "{ref}") (unit 1)))))''')
        ey = PWR_FLAG_Y + G
        items.append(wire(fx, PWR_FLAG_Y, fx, ey)); draw['wires'].append((fx, PWR_FLAG_Y, fx, ey))
        draw.setdefault('flags', []).append((net, fx, PWR_FLAG_Y))
        if net == 'GND':
            place_gnd(fx, ey)
        else:
            items.append(f'(label "{net}" (at {fmt(fx)} {fmt(ey)} 0) (fields_autoplaced) '
                         f'(effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{U()}"))')
            draw['labels'].append((net, fx, ey, 0))
    items.append(f'(text "PWR_FLAG: these nets are fed through passive parts (diodes, R4, L1, J1), so ERC needs a flag" '
                 f'(at {fmt(86.36)} {fmt(PWR_FLAG_Y + 2.54)} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{U()}"))')

    # block frames + titles + notes
    for title, x0, y0, x1, y1 in BLOCKS:
        items.append(f'(rectangle (start {fmt(x0)} {fmt(y0)}) (end {fmt(x1)} {fmt(y1)}) '
                     f'(stroke (width 0.2) (type dash)) (fill (type none)) (uuid "{U()}"))')
        items.append(f'(text "{title}" (at {fmt(x0 + 1.5)} {fmt(y0 + 2.5)} 0) '
                     f'(effects (font (size 1.8 1.8) (thickness 0.36) bold) (justify left bottom)) (uuid "{U()}"))')
    ny = 238.76
    for i, n in enumerate(NOTES):
        items.append(f'(text "{n}" (at 172.72 {fmt(ny + i * 3.2)} 0) '
                     f'(effects (font (size 1.5 1.5)) (justify left bottom)) (uuid "{U()}"))')
        draw['texts'].append((n, 172.72, ny + i * 3.2))

    libs = '\n'.join(lib_symbol_sexpr(k) for k in sorted(used_kinds))
    sch = f'''(kicad_sch (version 20230121) (generator eeschema)
(uuid "{root}")
(paper "A3")
(title_block (title "ESP32-S3 12 V Motor PWM Controller") (date "2026-10-26") (rev "1.0")
  (comment 1 "12 V car battery in (11-14.4 V), PWM low-side switched motor out, up to 10 A")
  (comment 2 "Generated from design.py - board and schematic share one netlist"))
(lib_symbols
{libs}
)
{chr(10).join(items)}
(sheet_instances (path "/" (page "1")))
)
'''
    return sch, draw

def wire(x1, y1, x2, y2):
    return f'(wire (pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)})) (stroke (width 0) (type default)) (uuid "{U()}"))'

# ---------------------------------------------------------------- PDF render (same geometry)
def render_pdf(draw, path):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle, Polygon, Arc
    fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 420); ax.set_ylim(297, 0); ax.axis('off')
    ax.add_patch(Rectangle((5, 5), 410, 287, fill=False, lw=0.8))
    col = '#7a0000'; wc = '#006400'
    def T(X, Y, x, y, k=1): return X + k * x, Y - k * y
    for b in draw['blocks']:
        t, x0, y0, x1, y1 = b
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ls='--', lw=0.5, ec='#888'))
        ax.text(x0 + 1.5, y0 + 2.5, t, fontsize=7.5, fontweight='bold', va='bottom', color='#333')
    for s in draw['symbols']:
        S = SYMS[s['kind']]; X, Y = s['X'], s['Y']; k = -1 if s.get('rot') == 180 else 1
        T0 = T
        T = lambda X, Y, x, y, T0=T0, k=k: T0(X, Y, x, y, k)
        for g in S['g']:
            if g[0] == 'rect':
                (x0, y0), (x1, y1) = T(X, Y, *g[1]), T(X, Y, *g[2])
                filled = len(g) > 3 and g[3]
                ax.add_patch(Rectangle((min(x0, x1), min(y0, y1)), abs(x1 - x0), abs(y1 - y0),
                                       fc=col if filled else '#fffbe6', ec=col, lw=0.6))
            elif g[0] == 'poly':
                pts = [T(X, Y, *p) for p in g[1]]
                if g[2]: ax.add_patch(Polygon(pts, closed=True, fc=col, ec=col, lw=0.6))
                else: ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=0.6)
            elif g[0] == 'circle':
                c = T(X, Y, *g[1]); ax.add_patch(Circle(c, g[2], fill=False, ec=col, lw=0.6))
            elif g[0] == 'arc':
                (sx, sy), (mx, my), (ex, ey) = g[1], g[2], g[3]
                c = T(X, Y, sx, (sy + ey) / 2); r = abs(sy - ey) / 2
                ax.add_patch(Arc(c, 2 * r, 2 * r, theta1=-90 if k > 0 else 90, theta2=90 if k > 0 else 270, ec=col, lw=0.6))
        for num, nm, x, y, ang, ln, et in S['pins']:
            if S['power']: continue
            ex, ey = T(X, Y, x, y)
            d = {0: (1, 0), 180: (-1, 0), 270: (0, 1), 90: (0, -1)}[ang]; d = (d[0] * k, d[1] * k)
            bx, by = ex + d[0] * ln, ey + d[1] * ln
            ax.plot([ex, bx], [ey, by], color=col, lw=0.6)
            if S['pnum']:
                ax.text((ex + bx) / 2, (ey + by) / 2 - 0.3, num, fontsize=3.2, ha='center', va='bottom', color=col)
            if S['pn'] and nm not in ('~',):
                if ang == 0: ax.text(bx + 0.6, by, nm, fontsize=3.8, va='center', ha='left', color='#004')
                elif ang == 180: ax.text(bx - 0.6, by, nm, fontsize=3.8, va='center', ha='right', color='#004')
        T = T0
        ref, rx, ry, j = s['ref']; val, vx, vy, _ = s['val']
        ha = 'left' if j == 'left' else 'center'
        ax.text(rx, ry, ref, fontsize=5, ha=ha, va='bottom', color='#00008b', fontweight='bold')
        ax.text(vx, vy, val, fontsize=4.5, ha=ha, va='bottom', color='#333')
    for x1, y1, x2, y2 in draw['wires']:
        ax.plot([x1, x2], [y1, y2], color=wc, lw=0.6)
    for net, x, y, ang in draw['labels']:
        if ang == 0: ax.text(x + 0.3, y - 0.3, net, fontsize=4.2, ha='left', va='bottom', color='#0000aa')
        elif ang == 180: ax.text(x - 0.3, y - 0.3, net, fontsize=4.2, ha='right', va='bottom', color='#0000aa')
        elif ang == 90: ax.text(x - 0.3, y - 0.3, net, fontsize=4.2, ha='left', va='bottom', rotation=90, color='#0000aa')
        else: ax.text(x - 0.3, y + 0.3, net, fontsize=4.2, ha='right', va='top', rotation=90, color='#0000aa')
    for x, y in draw['gnds']:
        ax.plot([x, x], [y, y + 1.27], color=col, lw=0.6)
        ax.add_patch(Polygon([(x - 1.27, y + 1.27), (x + 1.27, y + 1.27), (x, y + 2.54)], closed=True, fill=False, ec=col, lw=0.6))
    for x, y in draw['nc']:
        ax.plot([x - 0.6, x + 0.6], [y - 0.6, y + 0.6], color='#00f', lw=0.5)
        ax.plot([x - 0.6, x + 0.6], [y + 0.6, y - 0.6], color='#00f', lw=0.5)
    for n, x, y in draw['texts']:
        ax.text(x, y, n, fontsize=6, va='bottom')
    # title block
    ax.add_patch(Rectangle((300, 262), 115, 30, fill=False, lw=0.8))
    ax.text(302, 270, 'ESP32-S3 12 V Motor PWM Controller', fontsize=10, fontweight='bold')
    ax.text(302, 277, 'Rev 1.0   2026-10-26   Sheet 1/1   A3', fontsize=7)
    ax.text(302, 283, '12 V in (11-14.4 V)  ->  PWM low-side motor switch, up to 10 A', fontsize=6.5)
    ax.text(302, 288, 'Labels with the same name are connected.', fontsize=6, color='#555')
    fig.savefig(path)
    plt.close(fig)

def lib_file_sexpr():
    """The same symbols as a standalone library, so 'motor_ctrl:' resolves and they can be edited in KiCad."""
    syms = []
    for kind in sorted(SYMS):
        sx = lib_symbol_sexpr(kind)
        syms.append(sx.replace(f'(symbol "{sym_name(kind)}"', f'(symbol "{kind}"', 1))
    return '(kicad_symbol_lib (version 20220914) (generator kicad_symbol_editor)\n' + '\n'.join(syms) + '\n)\n'

SYM_LIB_TABLE = '''(sym_lib_table
  (lib (name "motor_ctrl")(type "KiCad")(uri "${KIPRJMOD}/motor_ctrl.kicad_sym")(options "")(descr "Symbols generated by gen_sch.py"))
)
'''

if __name__ == '__main__':
    import sys, os, shutil, subprocess
    sch, draw = build()
    out = sys.argv[1] if len(sys.argv) > 1 else 'out/motor_ctrl.kicad_sch'
    d = os.path.dirname(os.path.abspath(out))
    open(out, 'w').write(sch)
    open(os.path.join(d, 'motor_ctrl.kicad_sym'), 'w').write(lib_file_sexpr())
    open(os.path.join(d, 'sym-lib-table'), 'w').write(SYM_LIB_TABLE)
    pdf = out.replace('.kicad_sch', '_schematic.pdf')
    if shutil.which('kicad-cli'):     # KiCad's own plot
        subprocess.run(['kicad-cli', 'sch', 'export', 'pdf', '-o', pdf, out], check=True, capture_output=True)
    else:                             # approximate matplotlib drawing of the same geometry
        render_pdf(draw, pdf)
    print('wrote', out, 'motor_ctrl.kicad_sym, sym-lib-table and', os.path.basename(pdf))
