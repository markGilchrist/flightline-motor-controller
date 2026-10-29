# Project handoff: ESP32-S3 12 V motor PWM controller PCB

This file is the briefing for a Claude Code session picking up this project. It records what was asked for, every design decision and its reason, how the files were generated, what has been verified, and what is still open. Read it fully before changing anything.

---

## 1. The original request

> Design a PCB that takes a 12 V supply from a car battery (11–14 V), with a 12 V output to a motor. The PCB needs an ESP32 chip on it. I want to change the motor's speed and add pauses using the chip's PWM and a MOSFET.

Assumptions made because the request left them open (confirm with the user if you are changing the design):

| Topic | Assumption | Why |
|---|---|---|
| Motor current | **10 A continuous**, 15 A fuse | Originally assumed. **Session 2: the user confirmed the largest load is a windscreen wiper motor**: typically 2–5 A running at low speed, 4–8 A at high speed, 15–30 A stalled. Ratings kept. The 15 A fuse is the only stall protection (there is no current sensing), so a jammed wiper blows it within seconds. |
| Direction | **One direction only** (low-side switch, no H-bridge) | The request only mentioned speed and pauses. |
| Mounting | Low-side switching is OK | Session 2: the user said the motor is not in a car; it sits in another device and connects by spade connectors. It still must not have its case bonded to anything at battery negative (README says so). |
| Park switch | **Wanted** | Session 2: the user asked for the blades to park during pauses. J5 park input + firmware parking added. |
| ESP32 variant | **ESP32-S3-WROOM-1-N8 module** | Native USB on GPIO19/20, so no USB-UART chip is needed; the module is pre-certified with an antenna. |
| Programming | USB-C on the board | Works on the bench with no 12 V connected. |
| Copper | **2 oz**, 1.6 mm FR-4, 2 layers | Needed for the 4 mm power tracks to carry 10 A. |

---

## 2. Deliverables (current state)

The project root holds the deliverables (session 2 put it under local git; see §9). Generator scripts are in `generator_scripts/`.

| File | Status |
|---|---|
| `motor_ctrl.kicad_pro` | Project with net classes and design rules (KiCad 7/8/9). Re-saved by KiCad 7, so it carries KiCad's defaults. |
| `motor_ctrl.kicad_sch` | Single A3 sheet, generated, **KiCad 7 file format** (opens in 7/8/9). ERC 0/0. |
| `motor_ctrl.kicad_sym`, `sym-lib-table` | The generated symbols as a project library (`motor_ctrl:`) |
| `motor_ctrl.kicad_pcb` | Placed, routed, **zones filled**. KiCad DRC clean. Footprints are linked to symbols. Includes the J5 wiper park input. |
| `fab/gerbers/` | Gerbers (Cu, mask, paste, silk, edge), PTH/NPTH Excellon + drill maps, job file. From `make_fab.sh`. |
| `fab/motor_ctrl_pos.csv` | Pick-and-place, mm, origin = board bottom-left (aux origin set by `kicad_finish.py`) |
| `motor_ctrl_schematic.pdf` | Plotted by KiCad (`kicad-cli sch export pdf`) |
| `motor_ctrl_BOM.csv` | Bill of materials (`make_bom.py motor_ctrl_BOM.csv`) |
| `board_top.png`, `board_bottom.png` | gerbv renders of the Gerbers (copies of `fab/gerber_*.png`) |
| `firmware/motor_pwm/motor_pwm.ino` | Arduino-ESP32 core 3.x sketch |
| `firmware/test/` | Host build against a mock Arduino API + simulation tests (`sh firmware/test/run_tests.sh`) |
| `README.md` | User-facing build, wiring and flashing guide |

**Still not done:** no build with the real ESP32-S3 toolchain, and nothing has been opened in KiCad 8/9 (only 7.0.11). See §8.

---

## 3. Circuit description

Block diagram:

```
J1 (+12V,GND) → F1 15A blade → D1 TVS SMCJ20CA → Q1 P-FET (reverse polarity) → V12 rail
V12 → C1,C2 470µF bulk + C3,C4 10µF → J2 pin 2 (MOTOR+)
J2 pin 1 (MOTOR−) = MOTOR_N → Q2 N-FET drain;  Q2 source → GND
D3 dual Schottky: anodes on MOTOR_N, cathode on V12 (freewheel)
V12 →D5→ VIN_BUCK ←D6← VBUS (USB-C)   → U1 LMR33630 buck → +3V3
ESP32 GPIO4 (PWM) → U2 UCC27517A → R2 10Ω → Q2 gate
```

### Parts and the reasons for each

**Power entry**
- **J1, J2:** Phoenix MKDS 3/2-5.08 screw terminals.
- **F1:** 15 A mini blade fuse in a Keystone 3568 holder.
- **D1 SMCJ20CA:** 1500 W bidirectional TVS. Standoff voltage is 20 V, so it never conducts at a normal 14.4 V charging voltage, and it clamps load-dump spikes to about 32 V. Everything on the 12 V side is rated ≥ 35 V for this reason.
- **Q1 IPD90P04P4L-04:** −40 V P-MOSFET for reverse-polarity protection.
  - Drain is on the battery side (VBAT_F), source on V12. Gate goes to GND through R1 10k.
  - D2 BZT52C12 (cathode at the source) clamps Vgs to 12 V, because the FET's Vgs max is ±16 V.
- **C1, C2:** 470 µF 35 V low-ESR bulk caps (Panasonic EEU-FR1V471).
- **C3, C4:** 10 µF 50 V X7R 1210, for high-frequency decoupling next to the switch loop.

**Motor switch**
- **Q2 IPD90N04S4L-04:** 40 V, 3.8 mΩ logic-level N-MOSFET, low-side, in DPAK.
  - Conduction loss is about 0.4 W at 10 A.
- **D3 STPS20L45CG:** dual 2×10 A, 45 V Schottky in D2PAK, used as the freewheel diode across the motor. Tab = cathode = V12.
- **U2 UCC27517A:** single-channel 4 A low-side gate driver.
  - Its TTL input thresholds work with 3.3 V logic, so the gate can be switched quickly at 20 kHz.
  - IN− is tied to GND (non-inverting use).
- **Gate-driver supply (VDRV):** R4 220 Ω (1206) from V12, clamped by D4 BZT52C12 and decoupled by C5 1 µF and C6 100 nF.
  - D4 was originally BZT52C15. It was changed to 12 V because Q2's Vgs max is 16 V.
- **R2 10 Ω:** gate resistor.
- **R3 10k:** gate pull-down.
- **R5 100k:** pull-down on PWM. Keeps the motor off while the ESP32 boots or resets, or if the module is missing.

**3.3 V supply**
- **U1 TI LMR33630ADDAR:** 36 V, 3 A synchronous buck at 400 kHz, SO-PowerPAD-8.
  - Pinout: 1 PGND, 2 VIN, 3 EN, 4 PG (not connected), 5 FB, 6 VCC, 7 BOOT, 8 SW, 9 EP.
  - FB divider R7 100k / R8 43.2k with 1.0 V reference gives 3.31 V.
  - C10 100 nF bootstrap, C11 1 µF on VCC, R6 100k EN pull-up to VIN.
  - L1 Bourns SRP7028A-6R8M (6.8 µH). Output caps C12, C13 22 µF.
  - Input caps C7, C8 10 µF 50 V and C9 100 nF.
- **D5, D6 B360A:** OR the buck input from V12 or from USB VBUS, so the board can be programmed with only USB connected. The motor cannot run on USB power.

**ESP32-S3-WROOM-1 (U3)**
- C14 10 µF and C15 100 nF on 3V3.
- **EN:** R9 10k pull-up + C16 1 µF delay, with SW1 RESET to GND.
- **IO0:** R10 10k pull-up, with SW2 BOOT to GND.
- **Battery sense:** R13 100k / R14 18k (both 1%) plus C17 100 nF.
  - VSENSE = VBAT × 18/118, so 14.4 V reads 2.20 V.
  - Read with the ADC at 11 dB attenuation.
- **LEDs:** D7 green status LED via R15 1k on IO2; D8 red power LED via R16 1k on 3V3.
- **J4:** 1×4 header with 3V3, IO5, IO6, GND. Intended for a speed pot, button or sensor.

**Wiper park input (session 2)**
- **J5:** Phoenix PT 1,5/2-3,5-H, 3.5 mm pitch. Pin 1 PARK, pin 2 GND.
- **R17 4k7 (1206):** pull-up from V12 to PARK. An open contact reads 12 V, and the cam contact gets about 3 mA of wetting current (0.2 W at a 32 V load dump into a grounded contact).
- **R18 100k / R19 10k (1%):** PARK_ADC = PARK / 11, so 32 V → 2.9 V and no clamp is needed. **C18 470 nF:** τ = 9.1 k × 470 n = 4.3 ms. It removes the 20 kHz ripple that a 31b-style contact (switched to MOTOR_N) passes through.
- **IO7** (module pin 7, ADC1_CH6). The firmware compares PARK with the battery voltage (§6).

**USB-C (programming)**
- **J3:** HRO TYPE-C-31-M-12.
- **R11, R12:** 5.1k CC pull-downs. R11 is on CC2 and R12 on CC1; they were swapped during layout to suit placement, which makes no electrical difference.
- **U4 USBLC6-2SC6:** ESD protection on D+/D−. Pins 1 and 6 are D−, pins 3 and 4 are D+, pin 5 is VBUS, pin 2 is GND.

### ESP32-S3-WROOM-1 pin use

| Module pin | GPIO | Net | Function |
|---|---|---|---|
| 1, 40, 41 (EP) | — | GND | |
| 2 | — | +3V3 | |
| 3 | EN | EN | Reset |
| 4 | IO4 | PWM | Motor PWM out (LEDC, 20 kHz, 10-bit) |
| 5 | IO5 | IO5 | AUX J4 pin 2 (optional speed pot) |
| 6 | IO6 | IO6 | AUX J4 pin 3 |
| 7 | IO7 | PARK_ADC | Wiper park input (J5 via R18/R19/C18), ADC |
| 13 | IO19 | USB_DM | Native USB D− |
| 14 | IO20 | USB_DP | Native USB D+ |
| 27 | IO0 | IO0 | Boot strap / BOOT button |
| 38 | IO2 | LED | Status LED |
| 39 | IO1 | VSENSE | Battery voltage ADC |
| all others | | NC | Strapping pins 3, 45 and 46 are left at their internal defaults |

### Full netlist (ref.pad)

```
+3V3      C12.1 C13.1 C14.1 C15.1 J4.1 L1.2 R10.1 R16.1 R7.1 R9.1 U3.2
BOOT      C10.1 U1.7
CC1       J3.A5 R12.1
CC2       J3.B5 R11.1
EN        C16.1 R9.2 SW1.1 U3.3
EN_BUCK   R6.2 U1.3
FB        R7.2 R8.1 U1.5
GATE      Q2.1 R2.2 R3.1
GATE_DRV  R2.1 U2.5
GND       C1.2 C11.2 C12.2 C13.2 C14.2 C15.2 C16.2 C17.2 C2.2 C3.1 C4.1 C5.2 C6.1 C7.2 C8.2 C9.2 D1.1 D4.2 D7.1 D8.1
          J1.2 J3.A1 J3.A12 J3.B1 J3.B12 J3.S1 J4.4 Q2.3 R1.2 R11.2 R12.2 R14.2 R3.2 R5.2 R8.2 SW1.2 SW2.2
          U1.1 U1.9 U2.2 U2.4 U3.1 U3.40 U3.41 U4.2  C18.2 J5.2 R19.2
IO0       R10.2 SW2.1 U3.27
IO5       J4.2 U3.5
IO6       J4.3 U3.6
LED       R15.1 U3.38
LED_A     D7.2 R15.2
MOTOR_N   D3.1 D3.3 J2.1 Q2.2
PARK      J5.1 R17.2 R18.1
PARK_ADC  C18.1 R18.2 R19.1 U3.7
PWM       R5.1 U2.3 U3.4
PWR_A     D8.2 R16.2
QG_REV    D2.2 Q1.1 R1.1
SW        C10.2 L1.1 U1.8
USB_DM    J3.A7 J3.B7 U3.13 U4.1 U4.6
USB_DP    J3.A6 J3.B6 U3.14 U4.3 U4.4
V12       C1.1 C2.1 C3.2 C4.2 D2.1 D3.2 D5.2 J2.2 Q1.3 R13.1 R17.1 R4.1
VBAT_F    D1.2 F1.2 Q1.2
VBAT_IN   F1.1 J1.1
VBUS      D6.2 J3.A4 J3.A9 J3.B4 J3.B9 U4.5
VCC_BUCK  C11.1 U1.6
VDRV      C5.1 C6.2 D4.1 R4.2 U2.1
VIN_BUCK  C7.1 C8.1 C9.1 D5.1 D6.1 R6.1 U1.2
VSENSE    C17.1 R13.2 R14.1 U3.39
```

Pad numbering conventions used:
- Diodes and LEDs: pad 1 = cathode.
- TO-252 / TO-263: pad 1 = gate (or anode 1), pad 2 = tab, pad 3 = source (or anode 2).
- Polarised caps: pad 1 = +.

---

## 4. PCB layout

- **Board:** 92 × 76 mm, 2 layers. The KiCad sheet origin offset is (100, 100) mm, so board-relative (x, y) = KiCad (x−100, y−100).
- **Mounting holes:** four M3 holes at (4, 4), (88, 4), (4, 40), (88.5, 40).
- **Floor plan:**
  - Top half is logic: buck converter top-left, USB-C on the top edge at x≈44, ESP32 module top-right with its antenna overhanging the top edge region.
  - Antenna keepout, no copper on either layer: the ESP32 footprint's own rule area covers x 58–76, y 1.25–7.2. A board-level rule area added in session 2 (`build_pcb.py`, "antenna keepout to edge") extends it to x 57–77, y 0–7.2. Without it a 1 mm strip of GND pour ran along the antenna at the board edge.
  - Bottom half is power: J1 and F1 bottom-left, Q1, bulk caps, then Q2, D3 and J2 bottom-right.
- **Net classes** (defined in `design.py` → `NETCLASS`, mirrored in `.kicad_pro`):

| Class | Track | Clearance | Via | Nets |
|---|---|---|---|---|
| Power | 4.0 | 0.5 | 1.2/0.6 | VBAT_IN, VBAT_F, V12, MOTOR_N |
| GND | 0.6 | 0.25 | 0.8/0.4 | GND |
| Supply | 0.6 | 0.25 | 0.8/0.4 | +3V3, VIN_BUCK, VBUS, SW, VDRV, GATE, GATE_DRV, QG_REV |
| USB | 0.2 | 0.2 | 0.6/0.3 | USB_DP, USB_DM, CC1, CC2 |
| Default | 0.25 | 0.2 | 0.6/0.3 | everything else |

- **High-current copper:** hand-routed and locked, in `power_routes.py` (`TRACKS`, `VIAS`).
  - 4 mm top-layer tracks carry battery → fuse → Q1 → V12 bus at y≈38 → caps, D3 and J2.
  - A 5 mm bottom-layer GND bus runs from J1 to Q2's source.
  - V12 to J2 is duplicated on both layers. The bottom copy starts at the via at (82.4, 52.5), not under D3's top-only tab, which left a dangling end.
- **USB-C breakout:** also hand-routed and locked, in `power_routes.py` after the comment "USB-C breakout".
  - This connector has interleaved doubled D+/D− pads.
  - D+ pads B6 and A6 are joined below the pads, dropped to the bottom layer, and brought up into U4.3. U4.4 then goes on the top layer to ESP pin 14.
  - D− pads A7 and B7 each drop through a via above the pads, are joined on the bottom layer at y = 5.95 (kept ≥ 0.25 mm from the shell THT pads), and come up into U4.1. U4.6 then goes to ESP pin 13.
  - The two VBUS pads are joined on the bottom layer.
- **Everything else:** autorouted with **Freerouting 2.1.0** using a Specctra DSN written by `dsn.py`.
  - **GND is excluded from autorouting** (`SKIP_NETS` in `dsn.py`) and is carried by full GND pours on both layers instead.
  - Zones: clearance 0.4, min width 0.25, island removal on, `connect_pads thru_hole_only` (solid to SMD, thermal reliefs on THT).
  - Footprint overrides (session 2, `build_pcb.py`): **J3** clearance 0.2 mm, because the USB-C VBUS/GND pads are 0.2 mm apart by design against the 0.25 mm Supply class. **U1** zone connection solid, because its exposed-pad thermal vias starved with reliefs.
- **Ground fixes:** four GND pads that the top pour couldn't reach (C7/C8, C14/C15, D7/R14, C16) each got a short track plus a via down to the bottom pour (`fixgnd.py` → `fix_tracks`, `fix_vias`).
- **Stitching:** 132 GND stitching vias (0.6/0.3) on a 5 mm grid, placed only where both layers are solid pour (`stitch.py`). 128 remain after the park input (session 2).
- **Routing data:** `generator_scripts/routes_final.json` is the frozen session-1 route; keys `tracks`, `vias`, `fix_tracks`, `fix_vias`, `stitch`, in board-relative mm. **`routes_park.json`** = that plus the park-input tracks/vias, minus 4 stitching vias. **It is what the board is built from.**
- **Park input (session 2):** J5 at (61, 31.4) below the module, wire entry facing down. R17 at (68.5, 34.6) with its V12 pad overlapping the bus, like R13. R18/R19/C18 in a column at x 54, y 28–33. Routed by `route_extra.py` into `routes_park.json`: 11 tracks and 2 vias. PARK_ADC dives under the B.Cu PWM track and reaches IO7 on the top layer just inside the module's pad row. 4 stitching vias were removed: (52.5, 27.5), (52.5, 32.5), (62.5, 32.5), (67.5, 32.5).
- **Silkscreen:** `place_refs.py` deletes footprint silk arcs that actually overlap a pad (L1, J5; lines that only come close are kept, because on diodes they are the cathode mark). It then moves reference designators off pads and other silk and hides the mounting-hole refs. J4 has one label per pin.

---

## 5. Toolchain and how to regenerate

Scripts are in `generator_scripts/` (run them from the project root or that folder; paths below are from the project root). Everything is generated from one source of truth: **`design.py`** (parts, footprints, placement, pad→net maps, net classes, `sym_uuid()`).

| Script | Purpose |
|---|---|
| `design.py` | Parts list. Each `P(ref, value, footprint, x, y, rot, {pad: net}, kind, mpn, note)`. Board size, net classes. |
| `power_routes.py` | Locked hand-routed tracks and vias (power and USB). `all_vias()` returns `(net, x, y, size, drill)`. |
| `fplib.py`, `geom.py` | Load KiCad footprints via kiutils; absolute pad geometry; courtyards. Library paths come from `KICAD_FP_DIR` and `ESP_FP_DIR` (see Dependencies). |
| `dsn.py` | Writes the Specctra DSN (locked wires as `protect`; GND skipped) and reads the `.ses` result back. |
| `route.py` | Runs `java -jar freerouting-2.1.0.jar -de out/motor_ctrl.dsn -do out/motor_ctrl.ses -mp N`, then writes `out/routes.json`. Takes about 3–9 min. |
| `fixgnd.py in.json out.json` | Finds isolated GND pads and adds a pad → via link to the bottom pour. |
| `stitch.py in.json out.json` | Adds GND stitching vias. |
| `route_extra.py board routes_in.json routes_out.json` | (pcbnew) Two-layer grid A* (0.1 mm grid, net-class clearance + 0.06 mm) for small additions after the main route is frozen. Connections are listed in `CONNECTIONS`. Writes them as locked `fix_tracks`/`fix_vias` and drops stitching vias in the way. Used for the park input. |
| `build_pcb.py out.kicad_pcb routes.json` | Builds the `.kicad_pcb`: footprints with nets, MPN property and symbol path, outline, silk text, tracks, vias, GND zones, antenna keepout. Board file version 20221018 (KiCad 7). |
| `place_refs.py in.kicad_pcb out.kicad_pcb` | (pcbnew) Moves silk reference designators to clean spots. |
| `kicad_finish.py in.kicad_pcb out.kicad_pcb drc.rpt` | (pcbnew) Sets the drill/place origin, fills zones, saves, writes the KiCad DRC report and prints a summary. |
| `make_fab.sh [pcb] [outdir]` | (kicad-cli) Gerbers, drill files + maps and pick-and-place into `fab/`. |
| `gen_sch.py out.kicad_sch` | Builds the schematic in KiCad 7 format: embedded `motor_ctrl:` symbols, a wire stub plus net label on every pin, GND symbols, PWR_FLAGs, no-connects. Also writes `motor_ctrl.kicad_sym` and `sym-lib-table` next to it, and the PDF (kicad-cli if present, else matplotlib). UUIDs are deterministic, so regenerating is byte-identical. |
| `verify_sch.py` | Re-derives connectivity from the schematic geometry and compares it to `design.py`. Expected: 0 mismatches, 0 merged nets, 0 T-junctions, PWR_FLAGs not misplaced. |
| `compare_sch_pcb.py net pcb` | (pcbnew) KiCad-exported schematic netlist vs board: nets, values, footprints and symbol↔footprint links. Prints `MATCH`. |
| `run_erc_gui.sh /abs/path.kicad_sch` | Real KiCad 7 ERC, headless (Xvfb + xdotool click-through), writes `ERC.rpt`. On KiCad 8+ use `kicad-cli sch erc` instead. |
| `check.py [routes.json]` | Raster DRC at 0.025 mm per layer: shorts, clearance (routed copper only), edge clearance, simulated GND pour, connectivity. Writes `out/check.png`. |
| `exact_drc.py routes.json` | Exact vector clearance check (tracks/vias against everything; pads treated as rectangles, so it is conservative). |
| `make_bom.py` | Writes `out/motor_ctrl_BOM.csv`. |
| `render.py`, `render_final.py`, `preview.py` | Debug and fab-style renders. |

**Routing pipeline (session 1; not re-run in session 2):**

```bash
python3 route.py 120                                   # → out/routes.json
python3 fixgnd.py out/routes.json out/routes_fixed.json
# manual edit made: FB track y 20.3352 → 20.3852 (0.235 mm to C11 GND pad, needed 0.25)
python3 stitch.py out/routes_fixed.json out/routes_final.json
python3 exact_drc.py out/routes_final.json             # expect 0
python3 check.py out/routes_final.json                 # expect shorts [] and unconnected {}
```

**Build and check pipeline (session 2), from the project root:**

```bash
export KICAD_FP_DIR=/home/user/vendor/fp ESP_FP_DIR=/home/user/vendor/esp
G=generator_scripts; K=kicad_check; mkdir -p $K
python3 $G/build_pcb.py $K/unrouted.kicad_pcb $G/routes_final.json                 # new parts, not yet routed
(cd $G && python3 route_extra.py ../$K/unrouted.kicad_pcb routes_final.json routes_park.json)
python3 $G/build_pcb.py $K/built.kicad_pcb $G/routes_park.json
python3 $G/place_refs.py $K/built.kicad_pcb $K/placed.kicad_pcb
python3 $G/kicad_finish.py $K/placed.kicad_pcb motor_ctrl.kicad_pcb $K/drc.rpt   # expect "clean", 0 unconnected
sh $G/make_fab.sh
python3 $G/gen_sch.py motor_ctrl.kicad_sch && (cd $G && python3 verify_sch.py)
sh $G/run_erc_gui.sh $PWD/motor_ctrl.kicad_sch && mv ERC.rpt $K/                    # expect 0 errors 0 warnings
kicad-cli sch export netlist -o $K/motor_ctrl.net motor_ctrl.kicad_sch
python3 $G/compare_sch_pcb.py $K/motor_ctrl.net motor_ctrl.kicad_pcb                # expect MATCH
(cd $G && python3 make_bom.py ../motor_ctrl_BOM.csv)
sh firmware/test/run_tests.sh                                                       # expect ALL PASSED six times
```

`kicad_check/` is git-ignored scratch. The old render scripts were not re-run.

Re-running `route.py` gives a different route. If you re-route, redo the FB nudge and every later step. Also note that `fixgnd.py` and `stitch.py` run after routing, so moving parts invalidates them.

**Dependencies:**
- **KiCad 7.0.11** (Ubuntu 24.04 `apt install kicad`): pcbnew Python module, `kicad-cli`, eeschema. For headless ERC also `xvfb` and `xdotool`. `gerbv` for Gerber renders.
- **kiutils** 1.4.8 from PyPI (`pip install kiutils`).
- **Footprint libraries — exact versions matter.** The board was built from the **KiCad 5.1.12** `kicad-footprints` library, plus `SOT-23-5` and `SOT-23-6` from commit `55eb773dc2a8` of the same GitLab repo (Sep 2020, the scripted SOT-23 rewrite). Newer libraries change pad shapes (rect → roundrect) and SOT-23 pads, so the routing would no longer match. Session 2 rebuilt that mix in `/home/user/vendor/fp` (sparse clone of tag 5.1.12 plus the two files from the GitLab API) and confirmed the rebuild matches the delivered board apart from UUIDs.
- **Espressif library:** `ESP32-S3-WROOM-1.kicad_mod` from `espressif/kicad-libraries` main, in `/home/user/vendor/esp`.
- `fplib.py` reads `KICAD_FP_DIR` (folder of `*.pretty`) and `ESP_FP_DIR`; the defaults are the paths above.
- For routing only: Java 17+ with `freerouting-2.1.0.jar`; numpy, scipy, opencv-python, matplotlib and Pillow for the check/render scripts.

---

## 6. Firmware (`firmware/motor_pwm/motor_pwm.ino`)

- **Target:** Arduino-ESP32 core 3.x, board "ESP32S3 Dev Module", USB CDC On Boot = Enabled.
- **PWM:** `ledcAttach(4, 20000, 10)`, 20 kHz and 10-bit.
  - Any non-zero duty below `MIN_RUN_PCT` (18%) is lifted to 18% so the motor doesn't stall at very low duty.
- **FlightLine app (main control, session 2):** the board is a FlightLine Decoys controller for the user's own apps, `markGilchrist/flightline-ios` and `markGilchrist/flightline-android`. The protocol was taken from their code: `Protocol/ControllerCommand.swift`, `ControllerMessage.swift`, `Services/CoreBluetoothControllerService.swift`, `ControllerSession.swift`; Android `protocol/ControllerProtocol.kt`, `bluetooth/AndroidControllerLink.kt`.
  - BLE name `Flightline`, matched case-insensitively. Service `FFE0`, characteristic `FFE1` (HM-10 style), with props read/write/write-no-response/notify plus a `BLE2902` descriptor, which Android writes to enable notifications. Bluedroid only; NimBLE adds it itself.
  - The app writes 5-character ASCII commands without response. The board replies by notify, one reply per notification, with no terminator.
  - Commands: `aT?bb` → `ty<FL_DEVICE_TYPE>`. `aS?bb`/`aN?bb`/`aF?bb`/`aB?bb`/`aC?bb` → `sp<n>`/`on<n>`/`of<n>`/`XX<0|1>`/`xx<0|1>`. `aS###` speed, `aN###` on time, `aF###` off time (all 0–255; values above 255 are clamped). `axXXX`/`ayYYY` cycle on/off, `aXXXX`/`aYYYY` burst on/off.
  - Byte stream is parsed in 5-character chunks resynced on `a`, so split or joined writes work.
  - On connect the app sends `aT?bb`; on the type reply it writes all saved settings (`ControllerSession.writeAllSettings`).
  - **Behaviour (inferred from the app UI; confirm on the user's boards):**
    - Normal cycle: run at speed for the on time, then stop (park), then the off time, which counts from when stopped, then repeat.
    - Magnet (`FL_DEVICE_TYPE` 2): cycle on = run continuously. The app ramps the speed itself every 300 ms.
    - Burst: run continuously, overriding the cycle.
    - Speed raw/255 → %. French (3) always runs at 100%.
    - On time ms = n·100 + (255−n)·1000/255 with n ≥ 25, matching the app's display formula. Off time = n·100 ms.
  - Settings are kept in `Preferences` (`flightline` namespace: speed, on, off, cycle), written 2 s after the last change. Burst is not stored.
  - `Mode`: `MODE_APP` (start-up default, `START_MODE`), `MODE_PROGRAM` (USB `go`) and `MODE_MANUAL` (USB `s`/`stop`, pot). Any app *set* command switches to app mode.
  - USB serial accepts the same app commands, one per line, and prints the replies.
- **Step program (USB `go`):** the `program[]` table of `{speedPct, rampMs, holdMs}` loops forever. A speed of 0 is a pause. Ramps are linear.
- **Battery protection:** samples every 100 ms (16-sample average via `analogReadMilliVolts`).
  - Motor cuts below 10.5 V or above 16 V.
  - It resumes above 11.5 V (and below 15.5 V), **ramping up from 0**. The ramp is frozen at 0 while faulted (session 2 fix; before that it jumped straight back to the old duty).
- **Serial at 115200:** app commands, plus `s <0-100>` (manual), `r <ms>` ramp time, `go`, `stop`, and `v` (voltages, mode, Bluetooth state).
- **Optional pot:** set `USE_POT = true` to control speed from a pot on IO5 (J4). The pot sets the target and the output ramps to it over 300 ms; the bottom 2% of travel means off.
- **Status LED:** blinks slowly while running, fast on a fault.
- **Parking (`USE_PARK`, default on):** a program pause, `stop`, `s 0`, the pot at zero, or power-up in pot mode starts a park.
  - The motor ramps to `PARK_PCT` (70%) and runs until IO7 reads "parked" 3 samples in a row, then cuts. A pause's hold time counts from that moment.
  - "Parked" means park voltage (×11) < 0.5 × last battery reading, XOR `PARK_INVERT`. With 31b-style switches the parked level depends on duty, (1 − D) × Vbat, which is why the run to park is at 70%. The detection is only accepted once at speed.
  - `PARK_TIMEOUT_MS` (6 s): stop anyway and print `PARK: park position not seen`.
  - A battery fault mid-park sets `parkPending`, so the park resumes after recovery. `parkedKnown` stops a repeated stop from making an extra wipe.
  - `v` prints the park-input voltage and state.
- **Tests:** `firmware/test/run_tests.sh` compiles the sketch with host g++ (`-Wall -Wextra -Werror`) against `firmware/test/mock/Arduino.h`. That mock follows the arduino-esp32 3.3.x signatures for ledc, ADC, `min` and `constrain`. The tests run it in simulated time, with a wiper model: 300°/s crank, 15° park window, four park-switch types, and the R18‖R19×C18 filter. There are six builds: `app` (as shipped; the test plays the phone using the app's handshake, and checks every reply with a copy of the app's parser), `magnet` (`FL_DEVICE_TYPE` 2 with the app's speed ramp), `park` and `invert` (step program from power-up), `nopark` and `pot`. The mocks include BLE (`mock/BLEDevice.h`) and `Preferences` (flash that survives a simulated reboot).
- **Not yet compiled with the real ESP32-S3 toolchain:** the PlatformIO registry and dl.espressif.com were blocked in the session 2 environment.

---

## 7. Verification done

| Check | Result |
|---|---|
| **KiCad 7.0.11 DRC** after zone fill (`kicad_finish.py`) | **Clean**: 0 violations, 0 unconnected pads, with the park input. `lib_footprint_issues` only means no fp-lib-table on the build machine. The 2 raster-clearance flags from session 1 do not show in real DRC. |
| Antenna keepout | Probed the filled zones: 0 copper inside x 57.2–77, y 0.4–7.2 on both layers |
| **KiCad ERC** (eeschema 7.0.11) | 0 errors, 0 warnings (before PWR_FLAGs: 4 "power input not driven") |
| KiCad netlist vs board (`compare_sch_pcb.py`) | MATCH: 64/64 components (value + footprint), 32/32 nets, all symbol↔footprint links. Checked that it catches a swapped pin and a wrong value. |
| Schematic geometry vs `design.py` (`verify_sch.py`) | 0 mismatches, 0 merged nets, 0 T-junctions, 4 PWR_FLAGs on the right nets |
| Rebuild reproducibility | Rebuilding the delivered board with the pinned libraries matched it item for item apart from UUIDs. Session 2's board differs from the delivered one only by the intended changes (one V12 track, J3/U1 overrides, keepout, silk, paths). |
| Gerbers | Plotted by kicad-cli and rendered independently with gerbv (`fab/gerber_*.png`); vias, pours, keepout and silk checked visually |
| Firmware (host) | Compiles warning-free against the mock API; all simulation tests pass in the four builds, including parking with contact-to-GND, 31b and inverted switches, the unwired timeout and a fault mid-park |
| Electrical review (session 1) | Pinouts checked for ESP32-S3-WROOM-1, LMR33630 (SO PowerPAD), UCC27517A (SOT-23-5), USBLC6-2SC6, the TO-252/D2PAK tabs, and the P-FET orientation (drain on the battery side) |

---

## 8. Open items and recommended next steps (priority order)

Done in session 2: KiCad load, zone fill, DRC, ERC, symbol↔footprint linking, Gerbers and drill files, and host-side firmware tests (see §7, §9).

1. **Compile the firmware with the real toolchain** (Arduino IDE or arduino-cli, esp32 core 3.x, "ESP32S3 Dev Module"), then bench-test it with the FlightLine app on iOS and Android. Confirm the inferred cycle and burst behaviour (§6) matches the user's existing FlightLine boards. Note that a fresh iOS install has stored settings of 0, so its first connect writes speed 0. That is app behaviour: move the slider.
2. **Open the project once in KiCad 8 or 9**, the user's likely version. Everything was checked in 7.0.11 only. Expect a format-upgrade prompt. 3D models use `${KICAD8_3DMODEL_DIR}`; the ESP32's uses `${KICAD8_3RD_PARTY}`, so it only shows if the Espressif library is installed through KiCad's Plugin and Content Manager. Rerun DRC and ERC there. Run Update PCB from Schematic: it should report no changes, since footprint paths = symbol UUIDs.
3. **Bench-test parking with the user's actual wiper motor.** Identify its park terminals, check `v` readings at and away from park, and tune `PARK_PCT` if needed. Coasting is not modelled in the tests: a motor that overruns the park window after the cut would need a lower `PARK_PCT`, or braking.
4. Wiper stall (jammed arm) is the main overload case. Current sensing (below) would let the firmware stop before the fuse blows.
5. **Optional improvements discussed but not implemented:**
   - Swap the custom embedded symbols for standard KiCad symbols, keeping pin numbers.
   - Current sensing (shunt + amplifier into an ADC).
   - Reverse direction (H-bridge).
   - A clamp diode on VSENSE (a 32 V transient puts about 4.9 V on GPIO1, limited by R13 to ≈0.3 mA).
   - CAN or LIN, or an ignition-sense input.
   - Conformal coating for in-car use.
   - R4 sees about 1.8 W briefly during a load dump. It is fine for transients, but upsize it to a 2512 for margin.
6. **Before first power-up:** current-limited 12 V supply, no motor. Check the 3.3 V rail, then add the motor.

---

## 9. History (what happened in the original chat)

1. Parts were chosen and placed in `design.py`, and the power path was hand-routed in `power_routes.py`.
2. **First Freerouting run:** 12 connections unrouted. The USB-C pad field was tangled, and GND had been routed as tracks.
3. **Hand-routed USB-C breakout:**
   - Swapped the CC resistor nets (R11 → CC2, R12 → CC1).
   - Moved U4 to (50.5, 13.5, rot 270), R11 to (42.75, 14, 270), R12 to (45.25, 14, 270), R9 to (54, 15.8) and C16 to (54, 18.3).
   - Added a USB net class.
   - Fixed a V12 track that was too close to R13 (narrowed the last section to 0.8 mm).
4. **Second run:** 4 unrouted (EN, IO6, VCC_BUCK, VSENSE), blocked by autorouted GND tracks.
5. **GND excluded from routing:** all signals routed. 4 isolated GND pads were fixed with vias, one FB clearance was nudged, and stitching vias were added.
6. **D4 changed** from BZT52C15 to BZT52C12 (Q2 Vgs margin).
7. **Schematic generator written.** Fixed an IN− GND stub that would have landed on the VDD stub (a false short), and rotated GND-on-pin-1 passives by 180° so every GND uses a power symbol.

Backups of the pre-USB-fix files: `design_v1_backup.py`, `power_routes_v1_backup.py`. Earlier route sets: `routes_v1.json` (first run), `routes_v2.json` (second run), `routes.json` (GND-skipped run), `routes_fixed.json`, `routes_final.json`.

### Session 2 (KiCad verification and fab outputs)

The project is a local git repo; each step below is one commit. Nothing was pushed.

1. Installed KiCad 7.0.11 from Ubuntu. The KiCad 8/9 PPA, micromamba and arduino-cli downloads were blocked. Found the exact footprint library mix the board was built from (§5) and proved the rebuild reproduces it.
2. First real DRC: 8 USB-C clearance errors (pad pitch), 4 starved thermals on U1's EP vias, 1 dangling V12 track, about 60 silk items. Fixed at the source (`build_pcb.py`, `power_routes.py`, new `place_refs.py`). Zones are now filled in the delivered board.
3. Found in the Gerber render: GND pour between the antenna and the board edge. Added the board-level keepout to the edge.
4. Gerbers, drills and pick-and-place via `make_fab.sh`, with origin at the board's bottom-left.
5. The schematic was KiCad 8 format, so KiCad 7 couldn't read it. Switched `gen_sch.py` to the KiCad 7 format. The real ERC gave 4 power-not-driven errors; added PWR_FLAGs (GND, VIN_BUCK, +3V3, VDRV). Wrote a project symbol library, deterministic UUIDs, and footprint paths for linking. Readability fixes: vertical ref/value on two-pin parts, joined stacked pairs, chained GND pins, R16/D8 moved. The PDF is now plotted by KiCad.
6. Firmware: host mock and tests found a fault-recovery jump to full duty. Fixed it, and pot mode now ramps.
7. The user confirmed the motor is a windscreen wiper motor, mounted in a separate device (not a car), and asked for the blades to park. Added the J5 park input (R17/R18/R19/C18 → IO7), routed it with the new `route_extra.py` and made DRC fully clean (silk arcs over pads removed). Added firmware parking with tests for four switch types.
8. The user asked for the firmware to answer the FlightLine Controller apps, which are their own repos `flightline-ios` and `flightline-android`, attached read-only and not modified. Added BLE (FFE0/FFE1, name Flightline), the app protocol over BLE and USB, settings in flash, and app/program/manual modes. Tested with a mocked BLE stack that replays the app's handshake.
