#!/bin/sh
# Run KiCad 7 ERC headlessly (KiCad 7's kicad-cli has no ERC command; KiCad 8+ users can run
# `kicad-cli sch erc` instead). Drives eeschema on a virtual X display with xdotool.
# Usage: sh run_erc_gui.sh /abs/path/motor_ctrl.kicad_sch   -> writes ERC.rpt next to it.
# Needs: Xvfb, xdotool. Click positions match a 1600x1000 screen and KiCad 7.0 default window layout.
set -e
SCH=$1; DIR=$(dirname "$SCH")
export DISPLAY=:99
pgrep -x Xvfb >/dev/null || { Xvfb :99 -screen 0 1600x1000x24 >/dev/null 2>&1 & sleep 2; }
pkill -x eeschema || true; sleep 1; rm -f "$DIR"/~*.lck "$DIR/ERC.rpt"
(cd "$DIR" && setsid eeschema "$SCH" >/dev/null 2>&1 &)
sleep 20
xdotool mousemove 206 12 click 1; sleep 2       # Inspect menu
xdotool mousemove 282 37 click 1; sleep 3       # Electrical Rules Checker
xdotool mousemove 922 540 click 1; sleep 8      # Run ERC
xdotool mousemove 922 491 click 1; sleep 3      # Save...
xdotool mousemove 1137 798 click 1; sleep 3     # Save (default name ERC.rpt, schematic folder)
pkill -x eeschema || true
tail -1 "$DIR/ERC.rpt"
