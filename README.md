# ESP32-S3 12 V Motor PWM Controller (rev 1.0)

A 92 × 76 mm two-layer board that runs a 12 V DC motor from a car battery (11–14.4 V).
An ESP32-S3 sets the motor speed and adds pauses using PWM into a low-side MOSFET.

```
 Car battery ─► J1 ─► 15 A blade fuse ─► TVS (load-dump) ─► reverse-polarity P-FET ─► V12 rail
                                                                                      │
                       ┌──────────── 3.3 V buck (LMR33630) ◄── V12 or USB-C 5 V ──────┤
                       ▼                                                              ▼
                 ESP32-S3-WROOM-1 ── GPIO4 PWM ──► UCC27517 gate driver ──► N-MOSFET ──► J2 MOTOR −
                       │                                                     J2 MOTOR + ◄── V12
                       └── GPIO1 battery-voltage sense, GPIO2 status LED, USB-C for programming
```

## What's in this folder

| File | What it is |
|---|---|
| `motor_ctrl.kicad_pro / .kicad_sch / .kicad_pcb` | KiCad project (opens in KiCad 7, 8 or 9) |
| `motor_ctrl_schematic.pdf` | Schematic as a PDF |
| `motor_ctrl_BOM.csv` | Bill of materials |
| `board_top.png`, `board_bottom.png` | Renders of the routed board |
| `firmware/motor_pwm/motor_pwm.ino` | Arduino sketch: speed program with ramps and pauses |

## Key specs

- **Input:** 11–14.4 V car battery. Survives reverse battery (P-MOSFET Q1) and load-dump spikes (SMCJ20CA TVS clamps to about 32 V; everything on the 12 V side is rated 35–45 V).
- **Motor output:** 12 V, up to **10 A continuous**, fused at 15 A. Q2 (IPD90N04S4L-04, 3.8 mΩ) switches the motor's negative lead to ground, so the motor always sees full battery voltage scaled by the duty cycle.
- **PWM:** 20 kHz (silent), 10-bit, from GPIO4 through a UCC27517 4 A gate driver, so the MOSFET switches cleanly from a 3.3 V pin. R5 holds the motor **off** while the ESP32 boots or resets.
- **Freewheel diode:** D3 (STPS20L45CG, 2 × 10 A Schottky) across the motor absorbs the inductive kick at every PWM edge.
- **Logic power:** LMR33630 synchronous buck, 3.3 V / 3 A, runs from the battery or from USB-C. You can program the board on the bench with only a USB cable; the motor won't run without 12 V.
- **Extras:** battery-voltage sense on GPIO1 (low/high-voltage cut-out in firmware), status LED on GPIO2, power LED, RESET and BOOT buttons, and a 4-pin AUX header (3V3, GPIO5, GPIO6, GND) for a speed pot, button or sensor.

## Wiring

| Terminal | Pin 1 | Pin 2 |
|---|---|---|
| **J1 BATTERY** | +12 V (from battery +) | GND (battery −) |
| **J2 MOTOR** | MOTOR − | MOTOR + (+12 V) |

Use wire rated for your motor current (1.5 mm² / 16 AWG for 10 A), keep the battery leads short, and add an inline fuse at the battery end of the + lead as well.

## Making the board

1. Open `motor_ctrl.kicad_pro` in KiCad (free, kicad.org) and open the PCB.
2. Press **B** to fill the ground pours, then run **Inspect → Design Rules Checker**.
3. **File → Fabrication Outputs → Gerbers** (and **Drill Files**), zip them and upload to any PCB service (JLCPCB, PCBWay, OSH Park, Aisler…).
4. Order with **2 oz copper** and 1.6 mm thickness. The 10 A rating depends on the 4 mm power tracks being 2 oz.
5. All parts are standard footprints from the BOM. The SMD parts are 0603/0805 or larger, so you can hand-solder them. The SO-PowerPAD (U1) and the DPAK/D2PAK tabs need hot air or a hot plate.

## Firmware

1. Arduino IDE → install **esp32 by Espressif** (core 3.x).
2. Board: **ESP32S3 Dev Module**, **USB CDC On Boot: Enabled**.
3. Plug in USB-C. If the port doesn't appear, hold **BOOT**, tap **RESET**, release **BOOT**.
4. Upload `motor_pwm.ino`.

Edit the `program[]` table to set speed, ramp time and hold time for each step. A step with speed 0 is a pause. The sequence loops forever:

```cpp
Step program[] = {
  {  40, 1500, 5000 },   // ramp to 40 % over 1.5 s, run 5 s
  { 100, 2000, 8000 },   // ramp to full speed, run 8 s
  {   0, 1000, 3000 },   // ramp down, PAUSE 3 s
  ...
};
```

Over USB serial (115200 baud) you can also send `s 50` (set 50 %), `stop`, `go`, `r 500` (ramp time in ms) and `v` (battery voltage).

## Before you power it up

- Check the motor's **stall current**. A motor that draws more than about 15 A at start-up will blow the fuse. The MOSFET and diode can handle the surge; the fuse is there to protect the wiring.
- First power-up: use a current-limited bench supply at 12 V, no motor, and check that the 3.3 V rail and the power LED are OK. Then connect the motor.
- The motor's + lead is live whenever the battery is connected. PWM only switches the − side.
