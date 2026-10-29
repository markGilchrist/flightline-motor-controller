# Project handoff: ESP32-S3 12 V motor PWM controller PCB

This file is the briefing for a Claude Code session picking up this project. It records what was asked for, every design decision and its reason, how the files were generated, what has been verified, and what is still open. Read it fully before changing anything.

---

## 1. The original request

> Design a PCB that takes a 12 V supply from a car battery (11–14 V), with a 12 V output to a motor. The PCB needs an ESP32 chip on it. I want to change the motor's speed and add pauses using the chip's PWM and a MOSFET.

Assumptions made because the request left them open (confirm with the user if you are changing the design):

| Topic | Assumption | Why |
|---|---|---|
| Motor current | **10 A continuous**, 15 A fuse | The user gave no figure. 10 A covers most small 12 V automotive motors (pumps, fans, wipers, actuators). |
| Direction | **One direction only** (low-side switch, no H-bridge) | The request only mentioned speed and pauses. |
| ESP32 variant | **ESP32-S3-WROOM-1-N8 module** | Native USB on GPIO19/20, so no USB-UART chip is needed; the module is pre-certified with an antenna. |
| Programming | USB-C on the board | Works on the bench with no 12 V connected. |
| Copper | **2 oz**, 1.6 mm FR-4, 2 layers | Needed for the 4 mm power tracks to carry 10 A. |

---

## 2. Deliverables (current state)

All outputs are in `out/` in the working tree, and were also sent to the user in `ESP32_Motor_PWM_Controller.zip`.

| File | Status |
|---|---|
| `motor_ctrl.kicad_pro` | Project with net classes and design rules (KiCad 7/8/9) |
| `motor_ctrl.kicad_sch` | Single A3 sheet, generated. Its netlist was verified identical to the PCB. |
| `motor_ctrl.kicad_pcb` | Fully placed and routed, 2 GND zones (unfilled in the file; press **B** in KiCad) |
| `motor_ctrl_schematic.pdf` | PDF rendering of the schematic (drawn with matplotlib from the same geometry, not plotted by KiCad) |
| `motor_ctrl_BOM.csv` | Bill of materials |
| `board_top.png`, `board_bottom.png` | Raster renders including the simulated pour fill |
| `firmware/motor_pwm/motor_pwm.ino` | Arduino-ESP32 core 3.x sketch |
| `README.md` | User-facing build, wiring and flashing guide |

**Not yet done:**
- No Gerbers. KiCad was not available in the build environment.
- The board has never been opened in real KiCad.
- No KiCad DRC or ERC has been run (see §8).

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
          U1.1 U1.9 U2.2 U2.4 U3.1 U3.40 U3.41 U4.2
IO0       R10.2 SW2.1 U3.27
IO5       J4.2 U3.5
IO6       J4.3 U3.6
LED       R15.1 U3.38
LED_A     D7.2 R15.2
MOTOR_N   D3.1 D3.3 J2.1 Q2.2
PWM       R5.1 U2.3 U3.4
PWR_A     D8.2 R16.2
QG_REV    D2.2 Q1.1 R1.1
SW        C10.2 L1.1 U1.8
USB_DM    J3.A7 J3.B7 U3.13 U4.1 U4.6
USB_DP    J3.A6 J3.B6 U3.14 U4.3 U4.4
V12       C1.1 C2.1 C3.2 C4.2 D2.1 D3.2 D5.2 J2.2 Q1.3 R13.1 R4.1
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
  - An antenna keepout (no copper on either layer) covers x 56–78, y 0–7.4.
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
  - V12 to J2 is duplicated on both layers.
- **USB-C breakout:** also hand-routed and locked, in `power_routes.py` after the comment "USB-C breakout".
  - This connector has interleaved doubled D+/D− pads.
  - D+ pads B6 and A6 are joined below the pads, dropped to the bottom layer, and brought up into U4.3. U4.4 then goes on the top layer to ESP pin 14.
  - D− pads A7 and B7 each drop through a via above the pads, are joined on the bottom layer at y = 5.95 (kept ≥ 0.25 mm from the shell THT pads), and come up into U4.1. U4.6 then goes to ESP pin 13.
  - The two VBUS pads are joined on the bottom layer.
- **Everything else:** autorouted with **Freerouting 2.1.0** using a Specctra DSN written by `dsn.py`.
  - **GND is excluded from autorouting** (`SKIP_NETS` in `dsn.py`) and is carried by full GND pours on both layers instead.
  - Zones: clearance 0.4, min width 0.25, island removal on, `connect_pads thru_hole_only` (solid to SMD, thermal reliefs on THT).
- **Ground fixes:** four GND pads that the top pour couldn't reach (C7/C8, C14/C15, D7/R14, C16) each got a short track plus a via down to the bottom pour (`fixgnd.py` → `fix_tracks`, `fix_vias`).
- **Stitching:** 132 GND stitching vias (0.6/0.3) on a 5 mm grid, placed only where both layers are solid pour (`stitch.py`).
- **Final routing data:** `out/routes_final.json`, with keys `tracks`, `vias`, `fix_tracks`, `fix_vias`, `stitch`, in board-relative mm.

---

## 5. Toolchain and how to regenerate

The working tree is `/home/claude/gen` in the cloud session; the zip has the same scripts in `generator_scripts/`. Everything is generated from one source of truth: **`design.py`** (parts, footprints, placement, pad→net maps, net classes).

| Script | Purpose |
|---|---|
| `design.py` | Parts list. Each `P(ref, value, footprint, x, y, rot, {pad: net}, kind, mpn, note)`. Board size, net classes. |
| `power_routes.py` | Locked hand-routed tracks and vias (power and USB). `all_vias()` returns `(net, x, y, size, drill)`. |
| `fplib.py`, `geom.py` | Load KiCad footprints via kiutils; absolute pad geometry; courtyards. **`fplib.py` has hard-coded library paths, see below.** |
| `dsn.py` | Writes the Specctra DSN (locked wires as `protect`; GND skipped) and reads the `.ses` result back. |
| `route.py` | Runs `java -jar freerouting-2.1.0.jar -de out/motor_ctrl.dsn -do out/motor_ctrl.ses -mp N`, then writes `out/routes.json`. Takes about 3–9 min. |
| `fixgnd.py in.json out.json` | Finds isolated GND pads and adds a pad → via link to the bottom pour. |
| `stitch.py in.json out.json` | Adds GND stitching vias. |
| `build_pcb.py out.kicad_pcb routes.json` | Builds the `.kicad_pcb`: footprints with nets and MPN property, outline, silk text, tracks, vias, zones. Board file version 20221018. |
| `gen_sch.py out.kicad_sch` | Builds the KiCad 8 schematic (embedded custom `motor_ctrl:` lib symbols, a wire stub plus net label on every pin, GND power symbols, no-connect flags) and the PDF. |
| `verify_sch.py` | Re-derives connectivity from the schematic geometry and compares it to `design.py`. Expected: 0 mismatches, 0 merged nets, 0 T-junctions. |
| `check.py [routes.json]` | Raster DRC at 0.025 mm per layer: shorts, clearance (routed copper only), edge clearance, simulated GND pour, connectivity. Writes `out/check.png`. |
| `exact_drc.py routes.json` | Exact vector clearance check (tracks/vias against everything; pads treated as rectangles, so it is conservative). |
| `make_bom.py` | Writes `out/motor_ctrl_BOM.csv`. |
| `render.py`, `render_final.py`, `preview.py` | Debug and fab-style renders. |

**Pipeline used for the final board:**

```bash
export PYTHONPATH=<kiutils>/src
python3 route.py 120                                   # → out/routes.json
python3 fixgnd.py out/routes.json out/routes_fixed.json
# manual edit made: FB track y 20.3352 → 20.3852 (0.235 mm to C11 GND pad, needed 0.25)
python3 stitch.py out/routes_fixed.json out/routes_final.json
python3 exact_drc.py out/routes_final.json             # expect 0
python3 check.py out/routes_final.json                 # expect shorts [] and unconnected {}
python3 build_pcb.py out/motor_ctrl.kicad_pcb out/routes_final.json
python3 gen_sch.py out/motor_ctrl.kicad_sch && python3 verify_sch.py
python3 make_bom.py && python3 render_final.py
```

Re-running `route.py` gives a different route. If you re-route, redo the FB nudge and every later step. Also note that `fixgnd.py` and `stitch.py` run after routing, so moving parts invalidates them.

**Dependencies:**
- **kiutils:** run from source with `PYTHONPATH`.
- **Python packages:** numpy, scipy, opencv-python, matplotlib, Pillow.
- **Java 17+** with `freerouting-2.1.0.jar`.
- **KiCad footprint libraries** (official `kicad-footprints` repo) and the **Espressif KiCad library** (for `Espressif:ESP32-S3-WROOM-1`).
- In the cloud session these lived in `/home/claude/vendor/{kiutils,fp,esp,fr}`. **On a new machine, edit `fplib.py`** so `fp_path()` points at the local KiCad footprint folder and the Espressif `.pretty`.
- The build environment had no KiCad and no PyPI access, which is why DRC and fill were simulated rather than done in KiCad.

---

## 6. Firmware (`firmware/motor_pwm/motor_pwm.ino`)

- **Target:** Arduino-ESP32 core 3.x, board "ESP32S3 Dev Module", USB CDC On Boot = Enabled.
- **PWM:** `ledcAttach(4, 20000, 10)`, 20 kHz and 10-bit.
  - Any non-zero duty below `MIN_RUN_PCT` (18%) is lifted to 18% so the motor doesn't stall at very low duty.
- **Speed program:** the `program[]` table of `{speedPct, rampMs, holdMs}` loops forever. A speed of 0 is a pause. Ramps are linear.
- **Battery protection:** samples every 100 ms (16-sample average via `analogReadMilliVolts`).
  - Motor cuts below 10.5 V or above 16 V.
  - It resumes above 11.5 V (and below 15.5 V).
- **Serial at 115200:** `s <0-100>` sets speed and stops the program, `r <ms>` sets the ramp time, `go`, `stop`, `v` prints the voltage.
- **Optional pot:** set `USE_POT = true` to control speed from a pot on IO5 (J4).
- **Status LED:** blinks slowly while running, fast on a fault.
- Not compiled in this environment. **Compile and test it.**

---

## 7. Verification done

| Check | Result |
|---|---|
| Schematic netlist vs `design.py` (`verify_sch.py`) | 0 mismatches, 0 accidental merges, no wire T-junctions |
| Raster connectivity including the simulated GND pour (`check.py`) | All nets connected, no shorts, no edge violations |
| Exact clearance (`exact_drc.py`) | 0 violations |
| Raster clearance | 2 flags (BOOT/VCC_BUCK near U1 at (19.4, 14.5); EN/PWM near U3 at (57.2, 13.1)). Both are sampling artefacts; the exact check passes them. Confirm in KiCad DRC. |
| Courtyard overlaps / parts outside the board (`preview.py`) | None |
| Footprint pads vs pin maps | Every pad has a pin entry (mounting holes excluded) |
| Electrical review | Pinouts checked for ESP32-S3-WROOM-1, LMR33630 (SO PowerPAD), UCC27517A (SOT-23-5), USBLC6-2SC6, the TO-252/D2PAK tabs, and the P-FET orientation (drain on the battery side) |

---

## 8. Open items and recommended next steps (priority order)

1. **Open in KiCad 8/9.** Check that the `.kicad_pcb`, `.kicad_sch` and `.kicad_pro` load cleanly. The files were written by kiutils and hand-built s-expressions and have never been opened in KiCad. Watch for:
   - Footprint 3D model paths (rewritten to `${KICAD8_3DMODEL_DIR}`).
   - The ESP32 footprint's embedded keepout zone.
   - Net-class pattern assignment from `.kicad_pro`.
2. **Fill zones (B) and run KiCad DRC.** Fix anything the simulated checks missed: thermal-relief spoke failures on THT GND pads, silk over pads, courtyard rules, solder-mask bridges at the 0.5 mm-pitch USB-C pads.
3. **Run ERC on the schematic.**
   - Expected warnings: power-input pins not driven (add `PWR_FLAG` on V12, +3V3, GND and VBUS), and label-only nets.
   - The custom lib symbols are embedded in the schematic. Consider swapping in standard KiCad symbols, keeping pin numbers the same.
4. **Do Update PCB from Schematic** in KiCad to link symbols to footprints (UUIDs). The board and schematic were generated separately, so they aren't yet annotated together. Check that it only reports matching, with no changes.
5. **Generate Gerbers and drill files**, and preview them in KiCad's Gerber viewer or the fab house's viewer.
6. **Compile the firmware.**
7. **Confirm the motor's real continuous and stall current with the user.**
   - Above 10 A continuous: widen the power tracks or add copper pours on both layers, and reconsider the fuse.
   - Stall above about 15 A: add soft-start (the firmware already ramps) or a larger fuse.
8. **Optional improvements discussed but not implemented:**
   - Current sensing (shunt + amplifier into an ADC).
   - Reverse direction (H-bridge).
   - A clamp diode on VSENSE (a 32 V transient puts about 4.9 V on GPIO1, limited by R13 to ≈0.3 mA).
   - CAN or LIN, or an ignition-sense input.
   - Conformal coating for in-car use.
   - R4 sees about 1.8 W briefly during a load dump. It is fine for transients, but upsize it to a 2512 for margin.
9. **Before first power-up:** current-limited 12 V supply, no motor. Check the 3.3 V rail, then add the motor.

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
