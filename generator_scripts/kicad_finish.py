"""Fill zones and run KiCad DRC.  Usage: python3 kicad_finish.py in.kicad_pcb out.kicad_pcb drc.rpt
Needs KiCad's pcbnew Python module (KiCad 7+). The .kicad_pro next to out.kicad_pcb supplies net classes."""
import sys, re, shutil, os
import pcbnew

src, dst, rpt = sys.argv[1:4]
pro = os.path.join(os.path.dirname(os.path.abspath(dst)), os.path.splitext(os.path.basename(dst))[0] + '.kicad_pro')
if not os.path.exists(pro):
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'motor_ctrl.kicad_pro'), pro)
shutil.copy(src, dst)
b = pcbnew.LoadBoard(dst)          # load from dst so the matching .kicad_pro is picked up
# drill/place origin at the board's bottom-left corner, so fab files use board coordinates
pts = [q for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for q in (d.GetStart(), d.GetEnd())]
b.GetDesignSettings().SetAuxOrigin(pcbnew.VECTOR2I(min(q.x for q in pts), max(q.y for q in pts)))
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(dst)
b = pcbnew.LoadBoard(dst)
pcbnew.WriteDRCReport(b, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
txt = open(rpt).read()
kinds = {}
for k in re.findall(r'^\[(\w+)\]', txt, re.M):
    kinds[k] = kinds.get(k, 0) + 1
kinds.pop('lib_footprint_issues', None)   # only means no fp-lib-table is configured on this machine
print('DRC (excluding lib_footprint_issues):', kinds or 'clean')
print(re.search(r'Found \d+ unconnected pads', txt).group(0))
