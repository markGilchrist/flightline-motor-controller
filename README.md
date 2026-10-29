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
| `motor_ctrl.kicad_pro / .kicad_sch / .kicad_pcb` | KiCad project (opens in KiCad 7, 8 or 9). Ground pours are already filled. |
| `motor_ctrl.kicad_sym`, `sym-lib-table` | The project's schematic symbols, so KiCad finds and can edit them |
| `motor_ctrl_schematic.pdf` | Schematic as a PDF (plotted by KiCad) |
| `fab/gerbers/` | **Ready-to-order** Gerbers, drill files and drill maps |
| `fab/motor_ctrl_pos.csv` | Pick-and-place file (mm, origin at the board's bottom-left corner) |
| `motor_ctrl_BOM.csv` | Bill of materials |
| `board_top.png`, `board_bottom.png` | Renders of the Gerber files (top and bottom copper, silkscreen, drills) |
| `firmware/motor_pwm/motor_pwm.ino` | Arduino sketch: speed program with ramps and pauses |
| `firmware/test/` | Host-side tests for the sketch's logic (`sh firmware/test/run_tests.sh`, needs g++) |

## Key specs

- **Input:** 11–14.4 V car battery. Survives reverse battery (P-MOSFET Q1) and load-dump spikes (SMCJ20CA TVS clamps to about 32 V; everything on the 12 V side is rated 35–45 V).
- **Motor output:** 12 V, up to **10 A continuous**, fused at 15 A. Q2 (IPD90N04S4L-04, 3.8 mΩ) switches the motor's negative lead to ground, so the motor always sees full battery voltage scaled by the duty cycle.
- **PWM:** 20 kHz (silent), 10-bit, from GPIO4 through a UCC27517 4 A gate driver, so the MOSFET switches cleanly from a 3.3 V pin. R5 holds the motor **off** while the ESP32 boots or resets.
- **Freewheel diode:** D3 (STPS20L45CG, 2 × 10 A Schottky) across the motor absorbs the inductive kick at every PWM edge.
- **Logic power:** LMR33630 synchronous buck, 3.3 V / 3 A, runs from the battery or from USB-C. You can program the board on the bench with only a USB cable; the motor won't run without 12 V.
- **Wiper park input:** J5 takes the motor's park-switch contact (12 V tolerant, read on GPIO7), so pauses can stop the blades in the parked position.
- **Extras:** battery-voltage sense on GPIO1 (low/high-voltage cut-out in firmware), status LED on GPIO2, power LED, RESET and BOOT buttons, and a 4-pin AUX header (3V3, GPIO5, GPIO6, GND) for a speed pot, button or sensor.

## Wiring

| Terminal | Pin 1 | Pin 2 |
|---|---|---|
| **J1 BATTERY** | +12 V (from battery +) | GND (battery −) |
| **J2 MOTOR** | MOTOR − | MOTOR + (+12 V) |
| **J5 PARK** | Park-switch contact | GND |

Use wire rated for your motor current (1.5 mm² / 16 AWG for 10 A), keep the battery leads short, and add an inline fuse at the battery end of the + lead as well.

### Using a windscreen wiper motor

- Connect J2 pin 2 (+12 V) to the motor's **low-speed** terminal and J2 pin 1 (MOTOR −) to its **ground/common** terminal. Leave the high-speed terminal unconnected. Terminal numbering varies between makers, so identify them on a bench supply first.
- **Mounting:** the board switches the motor's negative wire. If the motor's ground terminal is connected to its metal case, the case must not touch anything wired to battery negative (a metal frame, a car body). Otherwise the motor gets its ground directly and the board can't stop it. Check with a meter between the ground terminal and the case.
- Typical currents: 2–8 A running, 15–30 A if the arm is jammed or frozen. A jam blows the 15 A fuse within a few seconds, which protects the board.

**Park switch (J5).** With it connected, every pause, `stop` command and the pot turned to zero first runs the wiper on to its park position, then stops.

- **Park contact that closes to ground at park:** wire it between J5 pin 1 and J5 pin 2 (GND).
- **Car-style motor with a 31b park terminal** (it switches between 53a and the motor's ground): wire **31b to J5 pin 1** only. 53a can stay unconnected.
- **Contact that opens at park:** wire it like the first case and set `PARK_INVERT = true` in the sketch.
- To check the wiring, send `v` over USB serial with 12 V connected. It reports the park-input voltage and whether it reads "at park". Move the blades by hand, or run the motor slowly with `s 30`, and watch it change.
- If the firmware never sees the park position within 6 s (for example J5 isn't wired), it stops the motor where it is and prints a warning. Set `USE_PARK = false` if you don't use the park switch.

## Making the board

1. Zip the contents of `fab/gerbers/` and upload it to any PCB service (JLCPCB, PCBWay, OSH Park, Aisler…). Check the preview the fab shows you against `board_top.png` / `board_bottom.png`.
2. Order with **2 oz copper** and 1.6 mm thickness. The 10 A rating depends on the 4 mm power tracks being 2 oz.
3. Board checks already done in KiCad: DRC has no copper, clearance or courtyard errors and no unconnected pads. The only remaining items are four silkscreen warnings from the inductor L1's own library outline, which the fab trims automatically. ERC has 0 errors and 0 warnings, and the schematic and board netlists match.
4. If you change the board in KiCad, press **B** to refill the pours, rerun **Inspect → Design Rules Checker**, and plot new Gerbers with **File → Fabrication Outputs**.
5. All parts are standard footprints from the BOM. The SMD parts are 0603/0805 or larger, so you can hand-solder them. The SO-PowerPAD (U1) and the DPAK/D2PAK tabs need hot air or a hot plate.

## Firmware

1. Arduino IDE → install **esp32 by Espressif** (core 3.x).
2. Board: **ESP32S3 Dev Module**, **USB CDC On Boot: Enabled**.
3. Plug in USB-C. If the port doesn't appear, hold **BOOT**, tap **RESET**, release **BOOT**.
4. Upload `motor_pwm.ino`.

### Using the FlightLine Controller app

The board works with the **FlightLine Controller** app (iOS and Android). It advertises over Bluetooth as **Flightline**, so switch it on and it appears as a card in the app.

- **Off/On (normal cycle):** runs at the set speed for the on time, parks the wiper, waits the off time, and repeats.
- **Quick Burst:** runs continuously at the set speed until you switch it off.
- **Speed, On Time, Off Time sliders:** take effect straight away.
- The board saves the speed, times and Off/On switch, so after a power cut it carries on as it was. Quick Burst always starts off.
- The board shows up in the app as a **Flapper**. To make it a **Magnet** (Off/On just runs at the set speed, with no on/off times) or a **French flapper**, change `FL_DEVICE_TYPE` near the top of the sketch to 2 or 3.

The same commands also work over USB serial (115200 baud), one per line, which is handy for testing without a phone. For example, `aS128` sets the speed to 128/255 and `aS?bb` asks for it back. The full list is at the top of the sketch.

Also over USB: `s 50` runs the motor at 50 % (manual), `stop` parks and stops, `r 500` sets the ramp time for `s` in ms, and `v` prints the battery and park-input voltages, the mode and the Bluetooth state. `go` runs the built-in step program in the `program[]` table (speed, ramp time and hold time per step; speed 0 is a pause). Any app command switches back to app control.

If the battery drops below 10.5 V or rises above 16 V, the motor stops and the status LED blinks fast. It restarts on its own once the battery is back between 11.5 V and 15.5 V, ramping up from zero rather than jumping straight back to speed. On USB power alone the firmware sees no battery, so the motor stays off.

## Before you power it up

- Check the motor's **stall current**. A motor that draws more than about 15 A at start-up will blow the fuse. The MOSFET and diode can handle the surge; the fuse is there to protect the wiring.
- First power-up: use a current-limited bench supply at 12 V, no motor, and check that the 3.3 V rail and the power LED are OK. Then connect the motor.
- The motor's + lead is live whenever the battery is connected. PWM only switches the − side.
