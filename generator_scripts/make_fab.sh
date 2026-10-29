#!/bin/sh
# Plot Gerbers, Excellon drill files and the pick-and-place file from the filled board.
# Usage: sh make_fab.sh [board.kicad_pcb] [out_dir]   (needs kicad-cli, KiCad 7+)
set -e
PCB=${1:-motor_ctrl.kicad_pcb}
OUT=${2:-fab}
rm -rf "$OUT/gerbers"; mkdir -p "$OUT/gerbers"
kicad-cli pcb export gerbers -o "$OUT/gerbers/" --use-drill-file-origin --subtract-soldermask \
  --layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts "$PCB"
kicad-cli pcb export drill -o "$OUT/gerbers/" --drill-origin plot --excellon-separate-th \
  --generate-map --map-format pdf "$PCB"
kicad-cli pcb export pos -o "$OUT/motor_ctrl_pos.csv" --format csv --units mm --side both \
  --use-drill-file-origin "$PCB"
