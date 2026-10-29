"""Move silkscreen reference designators so they don't overlap pads, other silk, or the board edge.

Usage: python3 place_refs.py in.kicad_pcb out.kicad_pcb
Needs KiCad's pcbnew Python module (KiCad 7+). Run after build_pcb.py, before zone fill / DRC.
Each reference keeps its library position if that is already clean; otherwise candidates around
the footprint (sides and corners, 0/90 deg, 1.0 then 0.8 mm text) are tried nearest-first.
First, footprint silk outlines (lines/arcs, not text) that actually overlap a pad are deleted (the fab would clip
them anyway). Lines that only come close are kept: on diodes those carry the cathode marking.
"""
import sys, math
import pcbnew

MM = pcbnew.FromMM
SILK_GAP = MM(0.15)     # silk-to-silk
MASK_GAP = MM(0.15)     # silk-to-pad (covers the mask expansion)
EDGE_GAP = MM(0.5)
HIDE = ('H',)           # reference prefixes to hide (mounting holes)


def text_shape(t):
    return t.GetEffectiveTextShape()


def main(src, dst):
    b = pcbnew.LoadBoard(src)
    pads = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            for silk, cu in ((pcbnew.F_SilkS, pcbnew.F_Cu), (pcbnew.B_SilkS, pcbnew.B_Cu)):
                if pad.IsOnLayer(cu):
                    pads[silk].append(pad.GetEffectiveShape(cu))
    dropped = []
    for fp in b.GetFootprints():
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() in pads and g.Type() != pcbnew.PCB_FP_TEXT_T and \
                    any(sp.Collide(g.GetEffectiveShape(), 0) for sp in pads[g.GetLayer()]):
                fp.Remove(g); dropped.append(fp.GetReference())
    edge = b.GetBoardEdgesBoundingBox()
    inner = pcbnew.BOX2I(pcbnew.VECTOR2I(edge.GetX() + EDGE_GAP, edge.GetY() + EDGE_GAP),
                         pcbnew.VECTOR2I(edge.GetWidth() - 2 * EDGE_GAP, edge.GetHeight() - 2 * EDGE_GAP))

    # obstacles per silk layer: (shape, gap)
    obst = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            for silk, cu in ((pcbnew.F_SilkS, pcbnew.F_Cu), (pcbnew.B_SilkS, pcbnew.B_Cu)):
                if pad.IsOnLayer(cu) or pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    obst[silk].append((pad.GetEffectiveShape(cu), MASK_GAP))
        for g in fp.GraphicalItems():
            if g.GetLayer() in obst and g.Type() != pcbnew.PCB_FP_TEXT_T:
                obst[g.GetLayer()].append((g.GetEffectiveShape(), SILK_GAP))
        val = fp.Value()
        if val.IsVisible() and val.GetLayer() in obst:
            obst[val.GetLayer()].append((text_shape(val), SILK_GAP))
    for d in b.GetDrawings():
        if d.GetLayer() in obst:
            shp = text_shape(d) if d.Type() == pcbnew.PCB_TEXT_T else d.GetEffectiveShape()
            obst[d.GetLayer()].append((shp, SILK_GAP))

    def clean(t):
        bb = t.GetBoundingBox()
        if not inner.Contains(bb.GetOrigin()) or not inner.Contains(bb.GetEnd()):
            return False
        ts = text_shape(t)
        return not any(s.Collide(ts, gap) for s, gap in obst[t.GetLayer()])

    # place crowded parts first (most pads nearby), so they get first pick
    fps = sorted(b.GetFootprints(), key=lambda f: -f.GetBoundingBox(False, False).GetArea())
    moved, hidden, failed = [], [], []
    for fp in fps:
        ref = fp.Reference()
        name = fp.GetReference()
        if not ref.IsVisible() or ref.GetLayer() not in obst:
            continue
        if name.startswith(HIDE) and name[len(HIDE[0]):].isdigit():
            ref.SetVisible(False); hidden.append(name); continue
        if clean(ref):
            obst[ref.GetLayer()].append((text_shape(ref), SILK_GAP)); continue
        orig_pos, orig_ang, orig_size = ref.GetPosition(), ref.GetTextAngle(), ref.GetTextSize()
        bb = fp.GetBoundingBox(False, False)
        cx, cy = bb.GetCenter().x, bb.GetCenter().y
        hw, hh = bb.GetWidth() / 2, bb.GetHeight() / 2
        cands = []
        for size in (1.0, 0.8):
            th = MM(size)
            tw = th * 0.75 * len(name)          # rough width, only used for spacing candidates
            for ang in (0, 90):
                ew, eh = (tw, th) if ang == 0 else (th, tw)
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                    for extra in (MM(0.3), MM(1.0), MM(1.8)):
                        x = cx + dx * (hw + ew / 2 + extra)
                        y = cy + dy * (hh + eh / 2 + extra)
                        cands.append((size != 1.0, math.hypot(x - cx, y - cy), x, y, ang, size))
        cands.sort()
        for _, _, x, y, ang, size in cands:
            ref.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
            ref.SetTextThickness(MM(size * 0.15))
            ref.SetTextAngle(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
            ref.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            if clean(ref):
                moved.append(name)
                break
        else:
            ref.SetTextSize(orig_size); ref.SetTextAngle(orig_ang); ref.SetPosition(orig_pos)
            ref.SetTextThickness(int(orig_size.y * 0.15))
            failed.append(name)
        obst[ref.GetLayer()].append((text_shape(ref), SILK_GAP))

    b.Save(dst)
    print('silk outlines over pads removed:', len(dropped), sorted(set(dropped)))
    print('moved', len(moved), sorted(moved))
    print('hidden', hidden)
    print('no clean spot (left in place)', failed)


if __name__ == '__main__':
    main(*sys.argv[1:3])
