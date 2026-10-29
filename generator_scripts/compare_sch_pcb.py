"""Compare a KiCad-exported schematic netlist with the board: connectivity, footprints, values and the
symbol-to-footprint links (footprint path = "/" + symbol UUID) that Update PCB from Schematic relies on.

Usage: python3 compare_sch_pcb.py motor_ctrl.net motor_ctrl.kicad_pcb
Make the netlist with:  kicad-cli sch export netlist -o motor_ctrl.net motor_ctrl.kicad_sch
Needs KiCad's pcbnew Python module. Exit code 0 = identical.
"""
import sys, os, re
import pcbnew

net_path, pcb_path = sys.argv[1:3]
txt = open(net_path).read()

# components: (comp (ref "R1") (value "10k") (footprint "Lib:Name") ...)
sch_comp, sch_uuid = {}, {}
for block in re.split(r'\n\s*\(comp ', txt)[1:]:
    m = re.match(r'\(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*(?:\(footprint "([^"]*)"\))?', block)
    sch_comp[m.group(1)] = (m.group(2), m.group(3) or '')
    u = re.findall(r'\(tstamps "([0-9a-f-]{36})"\)', block)
    sch_uuid[m.group(1)] = u[0] if u else None

# nets: (net (code "1") (name "X") (node (ref "R1") (pin "1") ...) ...)
sch_groups = []
for block in re.split(r'\n\s*\(net \(code', txt)[1:]:
    nodes = frozenset(re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', block))
    if len(nodes) > 1:
        sch_groups.append(nodes)

b = pcbnew.LoadBoard(pcb_path)
pcb_comp, by_net, fp_paths = {}, {}, {}
for fp in b.GetFootprints():
    pcb_comp[fp.GetReference()] = (fp.GetValue(), str(fp.GetFPID().GetUniStringLibId()))
    fp_paths[fp.GetReference()] = fp.GetPath().AsString()
    for pad in fp.Pads():
        if pad.GetNetname():
            by_net.setdefault(pad.GetNetname(), set()).add((fp.GetReference(), pad.GetNumber()))
pcb_groups = [frozenset(v) for v in by_net.values() if len(v) > 1]

errors = 0
for ref in sorted(set(sch_comp) | set(pcb_comp)):
    s, p = sch_comp.get(ref), pcb_comp.get(ref)
    if s != p:
        errors += 1
        print(f'component {ref}: schematic {s}  board {p}')
for ref in sorted(sch_uuid):
    if ref in fp_paths and fp_paths[ref] != '/' + str(sch_uuid[ref]):
        errors += 1
        print(f'link {ref}: symbol uuid {sch_uuid[ref]}  footprint path {fp_paths[ref] or "(none)"}')
only_s = set(sch_groups) - set(pcb_groups)
only_p = set(pcb_groups) - set(sch_groups)
for g in only_s:
    errors += 1; print('net only in schematic:', sorted(g))
for g in only_p:
    errors += 1; print('net only on board:', sorted(g))
single = [n for n, v in by_net.items() if len(v) == 1]
print(f'{len(sch_comp)} schematic components, {len(pcb_comp)} board footprints; '
      f'{len(sch_groups)} schematic nets vs {len(pcb_groups)} board nets (2+ pins); '
      f'board single-pin nets: {single or "none"}')
print('MATCH' if errors == 0 else f'{errors} DIFFERENCES')
os._exit(1 if errors else 0)     # os._exit avoids a pcbnew teardown crash in some builds
