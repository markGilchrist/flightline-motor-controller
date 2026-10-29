import uuid, math, copy, json, sys
from kiutils.board import Board
from kiutils.items.common import Position, Net, Stroke, Effects, Font
from kiutils.items.brditems import Segment, Via
from kiutils.items.gritems import GrLine, GrText
from kiutils.items.zones import Zone, ZonePolygon, FillSettings, Hatch
from kiutils.items.common import Coordinate
from design import PARTS, W, H, OX, OY, NETCLASS
from geom import fp_of
import power_routes

U = lambda: str(uuid.uuid4())

def all_nets():
    names = set()
    for p in PARTS:
        for n in p['pins'].values():
            if n: names.add(n)
    order = ['GND', 'V12', 'VBAT_IN', 'VBAT_F', 'MOTOR_N', '+3V3']
    rest = sorted(n for n in names if n not in order)
    return [n for n in order if n in names] + rest

def make_board(routes=None):
    """routes: dict(tracks=[(net, layer, width, x1,y1,x2,y2)], vias=[(net,x,y,size,drill)]) in board-relative mm"""
    b = Board.create_new()
    b.version = '20221018'
    b.generator = 'pcbnew'
    b.general.thickness = 1.6
    nets = all_nets()
    netnum = {n: i + 1 for i, n in enumerate(nets)}
    for n in nets:
        b.nets.append(Net(number=netnum[n], name=n))

    for p in PARTS:
        fp = fp_of(p['fp'])
        fp.libId = p['fp']
        fp.tstamp = U()
        fp.position = Position(X=round(OX + p['x'], 4), Y=round(OY + p['y'], 4), angle=p['rot'] or None)
        for g in fp.graphicItems:
            if type(g).__name__ == 'FpText':
                if g.type == 'reference': g.text = p['ref']
                elif g.type == 'value': g.text = p['value']
                g.position.angle = (p['rot'] + (g.position.angle or 0)) % 360 or None
                if hasattr(g, 'tstamp'): g.tstamp = U()
            elif hasattr(g, 'tstamp'):
                g.tstamp = U()
        for pad in fp.pads:
            pad.position.angle = (p['rot'] + (pad.position.angle or 0)) % 360 or None
            num = str(pad.number)
            net = p['pins'].get(num) if num else None
            pad.net = Net(number=netnum[net], name=net) if net else None
            if hasattr(pad, 'tstamp'): pad.tstamp = U()
        for m in fp.models:
            m.path = m.path.replace('${KISYS3DMOD}', '${KICAD8_3DMODEL_DIR}')
        if p.get('mpn'):
            fp.properties['MPN'] = p['mpn']
        if p['ref'] == 'J3':
            fp.clearance = 0.2    # USB-C VBUS/GND pads are 0.2 mm apart by design
        if p['ref'] == 'U1':
            fp.zoneConnect = 2    # solid: exposed-pad thermal vias would starve with reliefs
        for z in getattr(fp, 'zones', []) or []:
            if hasattr(z, 'tstamp'): z.tstamp = U()
            if z.layers == ['*.Cu']:
                z.layers = ['F.Cu', 'B.Cu']   # kiutils writes a lone '*.Cu' as (layer ..), not (layers ..)
            # footprint-embedded zones are stored in board coordinates
            for poly in z.polygons:
                for c in poly.coordinates:
                    dx, dy = c.X, c.Y
                    r = math.radians(p['rot'])
                    rx, ry = dx * math.cos(r) + dy * math.sin(r), -dx * math.sin(r) + dy * math.cos(r)
                    c.X, c.Y = round(OX + p['x'] + rx, 4), round(OY + p['y'] + ry, 4)
        b.footprints.append(fp)

    # board outline
    pts = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        b.graphicItems.append(GrLine(start=Position(OX + x1, OY + y1), end=Position(OX + x2, OY + y2),
                                     layer='Edge.Cuts', width=0.1, tstamp=U()))
    # silkscreen labels
    def txt(s, x, y, size=1.2, layer='F.SilkS', angle=None):
        t = GrText(text=s, position=Position(OX + x, OY + y, angle), layer=layer, tstamp=U())
        t.effects = Effects(font=Font(width=size, height=size, thickness=size * 0.15))
        b.graphicItems.append(t)
    txt('+12V IN', 6.0, 75.0 - 12.5, 1.0); txt('GND', 11.08, 75.0 - 12.5, 1.0)
    txt('MOT-', 80.0, 75.0 - 12.5, 1.0); txt('MOT+', 85.08, 75.0 - 12.5, 1.0)
    txt('ESP32 MOTOR PWM v1.0', 46.0, 74.5, 1.2, 'B.SilkS')
    txt('15A BLADE', 9.0, 44.0, 1.0)
    txt('RST', 46.0, 28.2, 0.9); txt('BOOT', 85.0, 28.2, 0.9)
    # J4 is a vertical 1x4 header: one label per pin, left of the pads
    for i, name in enumerate(('3V3', 'IO5', 'IO6', 'GND')):
        txt(name, 85.1, 17.5 + 2.54 * i, 0.8)

    # tracks
    tracks = []
    for net, layer, w, poly in power_routes.TRACKS:
        for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
            tracks.append((net, layer, w, x1, y1, x2, y2, True))
    vias = [(n, x, y, s, d, True) for n, x, y, s, d in power_routes.all_vias()]
    if routes:
        tracks += [tuple(t) + (False,) for t in routes['tracks']]
        vias += [tuple(v) + (False,) for v in routes['vias']]
        vias += [tuple(v) + (False,) for v in routes.get('stitch', [])]
        tracks += [tuple(t) + (True,) for t in routes.get('fix_tracks', [])]
        vias += [tuple(v) + (True,) for v in routes.get('fix_vias', [])]
    for net, layer, w, x1, y1, x2, y2, locked in tracks:
        b.traceItems.append(Segment(start=Position(round(OX + x1, 4), round(OY + y1, 4)),
                                    end=Position(round(OX + x2, 4), round(OY + y2, 4)),
                                    width=w, layer=layer, net=netnum[net], tstamp=U(), locked=locked))
    for net, x, y, s, d, locked in vias:
        b.traceItems.append(Via(position=Position(round(OX + x, 4), round(OY + y, 4)), size=s, drill=d,
                                layers=['F.Cu', 'B.Cu'], net=netnum[net], tstamp=U(), locked=locked))

    # ground pours (top + bottom); antenna keepout comes from the ESP32 footprint
    for layer, prio in (('B.Cu', 0), ('F.Cu', 0)):
        z = Zone(net=netnum['GND'], netName='GND', layers=[layer], tstamp=U(), name='GND_' + layer[0],
                 hatch=Hatch(style='edge', pitch=0.5), priority=prio,
                 clearance=0.4, minThickness=0.25, filledAreasThickness=None, connectPads='thru_hole_only',
                 fillSettings=FillSettings(yes=True, thermalGap=0.4, thermalBridgeWidth=0.6,
                                           islandRemovalMode=0))
        m = 0.3
        z.polygons = [ZonePolygon(coordinates=[Coordinate(OX + m, OY + m), Coordinate(OX + W - m, OY + m),
                                               Coordinate(OX + W - m, OY + H - m), Coordinate(OX + m, OY + H - m)])]
        b.zones.append(z)
    return b, netnum

if __name__ == '__main__':
    routes = None
    if len(sys.argv) > 2:
        routes = json.load(open(sys.argv[2]))
    b, _ = make_board(routes)
    b.to_file(sys.argv[1])
    print('wrote', sys.argv[1])
