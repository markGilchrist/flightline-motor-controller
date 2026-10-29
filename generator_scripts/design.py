"""Single source of truth for the ESP32 PWM motor controller.
Each part: ref, value, footprint, (x, y, rot) relative to board top-left, pad->net map,
schematic symbol kind, manufacturer part number, short note."""

W, H = 92.0, 76.0          # board size (mm)
OX, OY = 100.0, 100.0      # board origin on the KiCad sheet

R0805 = 'Resistor_SMD:R_0805_2012Metric'
R1206 = 'Resistor_SMD:R_1206_3216Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
C1206 = 'Capacitor_SMD:C_1206_3216Metric'
C1210 = 'Capacitor_SMD:C_1210_3225Metric'

import uuid as _uuid
_NS = _uuid.UUID('6f3c2a1e-6b1d-4f6e-9a57-3c0d2b7e9a10')
def sym_uuid(ref):
    """Schematic symbol UUID for a part; build_pcb.py writes the same value as the footprint's path,
    which is how KiCad links a footprint to its symbol (Update PCB from Schematic)."""
    return str(_uuid.uuid5(_NS, 'symbol:' + ref))

def P(ref, value, fp, x, y, rot, pins, kind, mpn='', note=''):
    return dict(ref=ref, value=value, fp=fp, x=x, y=y, rot=rot, pins=pins, kind=kind, mpn=mpn, note=note)

PARTS = [
    # ---------------- power input + protection ----------------
    P('J1', 'BATTERY 12V', 'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal',
      6.0, 70.2, 0, {'1': 'VBAT_IN', '2': 'GND'}, 'conn2', 'Phoenix 1711026 (MKDS 3/2-5.08)', 'Battery in: 1 = +12V, 2 = GND'),
    P('F1', '15A', 'Fuse:Fuseholder_Blade_Mini_Keystone_3568', 4.0, 47.0, 0,
      {'1': 'VBAT_IN', '2': 'VBAT_F'}, 'fuse', 'Keystone 3568 + 15A mini blade fuse', ''),
    P('D1', 'SMCJ20CA', 'Diode_SMD:D_SMC', 18.0, 57.6, 90, {'1': 'GND', '2': 'VBAT_F'}, 'tvs',
      'Littelfuse SMCJ20CA', 'Bidirectional TVS, 1500 W'),
    P('Q1', 'IPD90P04P4L-04', 'Package_TO_SOT_SMD:TO-252-2', 26.0, 48.0, 180,
      {'1': 'QG_REV', '2': 'VBAT_F', '3': 'V12'}, 'pmos', 'Infineon IPD90P04P4L-04', 'Reverse-polarity protection, -40 V'),
    P('R1', '10k', R0805, 33.0, 53.0, 90, {'1': 'QG_REV', '2': 'GND'}, 'r', '', ''),
    P('D2', 'BZT52C12', 'Diode_SMD:D_SOD-123', 33.0, 48.0, 270, {'1': 'V12', '2': 'QG_REV'}, 'zener',
      'BZT52C12', 'Gate clamp for Q1'),
    P('C1', '470uF 35V', 'Capacitor_THT:CP_Radial_D10.0mm_P5.00mm', 41.0, 50.5, 270, {'1': 'V12', '2': 'GND'}, 'cp',
      'Panasonic EEU-FR1V471', 'Low-ESR bulk'),
    P('C2', '470uF 35V', 'Capacitor_THT:CP_Radial_D10.0mm_P5.00mm', 52.5, 50.5, 270, {'1': 'V12', '2': 'GND'}, 'cp',
      'Panasonic EEU-FR1V471', 'Low-ESR bulk'),
    P('C3', '10uF 50V', C1210, 60.0, 45.0, 90, {'1': 'GND', '2': 'V12'}, 'c', 'X7R 1210', 'HF decoupling at switch'),
    P('C4', '10uF 50V', C1210, 64.0, 45.0, 90, {'1': 'GND', '2': 'V12'}, 'c', 'X7R 1210', ''),
    # ---------------- motor switch ----------------
    P('Q2', 'IPD90N04S4L-04', 'Package_TO_SOT_SMD:TO-252-2', 72.5, 59.5, 0,
      {'1': 'GATE', '2': 'MOTOR_N', '3': 'GND'}, 'nmos', 'Infineon IPD90N04S4L-04', 'Logic-level, 40 V, 3.8 mOhm'),
    P('D3', 'STPS20L45CG', 'Package_TO_SOT_SMD:TO-263-2', 76.0, 46.0, 0,
      {'1': 'MOTOR_N', '2': 'V12', '3': 'MOTOR_N'}, 'dual_schottky', 'ST STPS20L45CG-TR', 'Motor freewheel diode, 2x10 A'),
    P('J2', 'MOTOR', 'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal',
      80.0, 70.2, 0, {'1': 'MOTOR_N', '2': 'V12'}, 'conn2', 'Phoenix 1711026 (MKDS 3/2-5.08)', 'Motor: 1 = MOTOR-, 2 = +12V'),
    P('U2', 'UCC27517A', 'Package_TO_SOT_SMD:SOT-23-5', 63.5, 65.5, 0,
      {'1': 'VDRV', '2': 'GND', '3': 'PWM', '4': 'GND', '5': 'GATE_DRV'}, 'driver', 'TI UCC27517ADBVR', '4 A low-side gate driver'),
    P('R2', '10R', R0805, 64.5, 57.5, 90, {'1': 'GATE_DRV', '2': 'GATE'}, 'r', '', 'Gate resistor'),
    P('R3', '10k', R0805, 67.0, 70.5, 0, {'1': 'GATE', '2': 'GND'}, 'r', '', 'Gate pull-down'),
    P('R4', '220R', R1206, 52.0, 70.5, 0, {'1': 'V12', '2': 'VDRV'}, 'r', '', 'Driver supply'),
    P('D4', 'BZT52C12', 'Diode_SMD:D_SOD-123', 57.0, 73.0, 0, {'1': 'VDRV', '2': 'GND'}, 'zener', 'BZT52C12', 'Clamps driver VDD to 12 V (MOSFET Vgs max 16 V)'),
    P('C5', '1uF 25V', C0805, 57.0, 68.5, 180, {'1': 'VDRV', '2': 'GND'}, 'c', '', ''),
    P('C6', '100nF', C0603, 60.0, 65.5, 90, {'1': 'GND', '2': 'VDRV'}, 'c', '', ''),
    P('R5', '100k', R0805, 63.5, 62.0, 180, {'1': 'PWM', '2': 'GND'}, 'r', '', 'Holds motor off during boot'),
    # ---------------- 3.3 V buck ----------------
    P('D5', 'B360A', 'Diode_SMD:D_SMA', 12.0, 36.0, 270, {'1': 'VIN_BUCK', '2': 'V12'}, 'schottky', 'Diodes B360A-13-F', ''),
    P('D6', 'B360A', 'Diode_SMD:D_SMA', 33.0, 21.0, 0, {'1': 'VIN_BUCK', '2': 'VBUS'}, 'schottky', 'Diodes B360A-13-F', 'USB power for programming'),
    P('C7', '10uF 50V', C1210, 7.0, 20.0, 90, {'1': 'VIN_BUCK', '2': 'GND'}, 'c', 'X7R 1210', ''),
    P('C8', '10uF 50V', C1210, 10.5, 20.0, 90, {'1': 'VIN_BUCK', '2': 'GND'}, 'c', 'X7R 1210', ''),
    P('C9', '100nF 50V', C0603, 8.5, 13.5, 0, {'1': 'VIN_BUCK', '2': 'GND'}, 'c', '', ''),
    P('U1', 'LMR33630ADDA', 'Package_SO:TI_SO-PowerPAD-8_ThermalVias', 15.5, 14.0, 0,
      {'1': 'GND', '2': 'VIN_BUCK', '3': 'EN_BUCK', '4': None, '5': 'FB', '6': 'VCC_BUCK', '7': 'BOOT', '8': 'SW', '9': 'GND'},
      'buck', 'TI LMR33630ADDAR', '36 V 3 A sync buck, 400 kHz'),
    P('R6', '100k', R0805, 11.0, 26.0, 0, {'1': 'VIN_BUCK', '2': 'EN_BUCK'}, 'r', '', ''),
    P('C10', '100nF', C0603, 20.5, 14.5, 90, {'1': 'BOOT', '2': 'SW'}, 'c', '', 'Bootstrap'),
    P('C11', '1uF', C0603, 17.5, 19.5, 0, {'1': 'VCC_BUCK', '2': 'GND'}, 'c', '', ''),
    P('L1', '6.8uH', 'Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm', 25.0, 7.0, 0, {'1': 'SW', '2': '+3V3'}, 'l',
      'Bourns SRP7028A-6R8M', ''),
    P('R7', '100k', R0805, 22.0, 20.0, 0, {'1': '+3V3', '2': 'FB'}, 'r', '1%', 'FB top'),
    P('R8', '43.2k', R0805, 22.0, 23.0, 0, {'1': 'FB', '2': 'GND'}, 'r', '1%', 'FB bottom: Vout = 1.0*(1+100/43.2)'),
    P('C12', '22uF 10V', C1206, 32.0, 6.0, 90, {'1': '+3V3', '2': 'GND'}, 'c', 'X7R 1206', ''),
    P('C13', '22uF 10V', C1206, 35.5, 6.0, 90, {'1': '+3V3', '2': 'GND'}, 'c', 'X7R 1206', ''),
    # ---------------- ESP32-S3 ----------------
    P('U3', 'ESP32-S3-WROOM-1', 'Espressif:ESP32-S3-WROOM-1', 67.0, 17.0, 0,
      {'1': 'GND', '2': '+3V3', '3': 'EN', '4': 'PWM', '5': 'IO5', '6': 'IO6', '13': 'USB_DM', '14': 'USB_DP',
       '27': 'IO0', '38': 'LED', '39': 'VSENSE', '40': 'GND', '41': 'GND'},
      'esp32', 'Espressif ESP32-S3-WROOM-1-N8', ''),
    P('C14', '10uF', C0805, 53.0, 9.0, 90, {'1': '+3V3', '2': 'GND'}, 'c', '', ''),
    P('C15', '100nF', C0603, 55.0, 12.5, 0, {'1': '+3V3', '2': 'GND'}, 'c', '', ''),
    P('R9', '10k', R0805, 54.0, 15.8, 0, {'1': '+3V3', '2': 'EN'}, 'r', '', ''),
    P('C16', '1uF', C0603, 54.0, 18.3, 0, {'1': 'EN', '2': 'GND'}, 'c', '', 'EN RC delay'),
    P('SW1', 'RESET', 'Button_Switch_SMD:SW_SPST_TL3342', 46.0, 32.0, 0, {'1': 'EN', '2': 'GND'}, 'sw', 'E-Switch TL3342F160QG', ''),
    P('SW2', 'BOOT', 'Button_Switch_SMD:SW_SPST_TL3342', 85.0, 32.0, 0, {'1': 'IO0', '2': 'GND'}, 'sw', 'E-Switch TL3342F160QG', ''),
    P('R10', '10k', R0805, 80.0, 26.0, 0, {'1': '+3V3', '2': 'IO0'}, 'r', '', ''),
    P('J3', 'USB-C', 'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12', 44.0, 4.4, 180,
      {'A1': 'GND', 'B12': 'GND', 'A12': 'GND', 'B1': 'GND', 'A4': 'VBUS', 'B9': 'VBUS', 'A9': 'VBUS', 'B4': 'VBUS',
       'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP', 'A7': 'USB_DM', 'B7': 'USB_DM',
       'A8': None, 'B8': None, 'S1': 'GND'},
      'usbc', 'HRO TYPE-C-31-M-12', 'Programming / debug'),
    P('R11', '5.1k', R0805, 42.75, 14.0, 270, {'1': 'CC2', '2': 'GND'}, 'r', '', ''),
    P('R12', '5.1k', R0805, 45.25, 14.0, 270, {'1': 'CC1', '2': 'GND'}, 'r', '', ''),
    P('U4', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6', 50.5, 13.5, 270,
      {'1': 'USB_DM', '2': 'GND', '3': 'USB_DP', '4': 'USB_DP', '5': 'VBUS', '6': 'USB_DM'}, 'esd', 'ST USBLC6-2SC6', 'USB ESD'),
    # ---------------- sensing, LEDs, spare IO ----------------
    P('R13', '100k', R0805, 72.0, 34.5, 90, {'1': 'V12', '2': 'VSENSE'}, 'r', '1%', 'Battery sense top'),
    P('R14', '18k', R0805, 82.0, 13.0, 0, {'1': 'VSENSE', '2': 'GND'}, 'r', '1%', 'Battery sense bottom'),
    P('C17', '100nF', C0603, 82.0, 10.5, 0, {'1': 'VSENSE', '2': 'GND'}, 'c', '', ''),
    P('D7', 'GREEN', 'LED_SMD:LED_0805_2012Metric', 82.0, 19.5, 180, {'1': 'GND', '2': 'LED_A'}, 'led', '', 'Status LED (IO2)'),
    P('R15', '1k', R0805, 82.0, 16.5, 180, {'1': 'LED', '2': 'LED_A'}, 'r', '', ''),
    P('D8', 'RED', 'LED_SMD:LED_0805_2012Metric', 20.0, 30.0, 0, {'1': 'GND', '2': 'PWR_A'}, 'led', '', 'Power LED'),
    P('R16', '1k', R0805, 25.0, 30.0, 0, {'1': '+3V3', '2': 'PWR_A'}, 'r', '', ''),
    P('J4', 'AUX', 'Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical', 88.0, 17.5, 0,
      {'1': '+3V3', '2': 'IO5', '3': 'IO6', '4': 'GND'}, 'conn4', '2.54 mm header', 'Spare: pot / button / sensor'),
    # ---------------- mechanical ----------------
    P('H1', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 4.0, 4.0, 0, {}, 'hole'),
    P('H2', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 88.0, 4.0, 0, {}, 'hole'),
    P('H3', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 4.0, 40.0, 0, {}, 'hole'),
    P('H4', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 88.5, 40.0, 0, {}, 'hole'),
]

# Net classes: (track width, clearance) in mm
POWER_NETS = {'VBAT_IN', 'VBAT_F', 'V12', 'MOTOR_N'}
NETCLASS = {
    'Default': dict(width=0.25, clearance=0.2, via=(0.6, 0.3)),
    'USB': dict(width=0.2, clearance=0.2, via=(0.6, 0.3), nets=['USB_DP', 'USB_DM', 'CC1', 'CC2']),
    'Supply': dict(width=0.6, clearance=0.25, via=(0.8, 0.4),
                   nets=['+3V3', 'VIN_BUCK', 'VBUS', 'SW', 'VDRV', 'GATE', 'GATE_DRV', 'QG_REV']),
    'GND': dict(width=0.6, clearance=0.25, via=(0.8, 0.4), nets=['GND']),
    'Power': dict(width=4.0, clearance=0.5, via=(1.2, 0.6), nets=sorted(POWER_NETS)),
}
