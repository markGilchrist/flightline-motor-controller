/*
  ESP32-S3 12 V motor PWM controller  -  firmware for the "motor_ctrl" PCB
  ------------------------------------------------------------------------
  Board:   ESP32S3 Dev Module (Arduino-ESP32 core 3.x)
           Tools > USB CDC On Boot: Enabled   (so Serial works over the USB-C port)
  Pins:    GPIO4  -> PWM to UCC27517 gate driver -> IPD90N04S4L-04 low-side MOSFET
           GPIO1  -> battery sense (100k / 18k divider)
           GPIO2  -> status LED
           GPIO5, GPIO6 -> spare (AUX header J4). GPIO5 can take a 10k speed pot.
           GPIO7  -> wiper park switch (J5, through a 1/11 divider)

  What it does
   - Works with the FlightLine Controller app (iOS and Android). The board advertises over Bluetooth LE
     as "Flightline" with the HM-10 style serial service the app looks for (FFE0 / FFE1), and answers
     the app's commands (see "FlightLine app protocol" below). The app sets the speed, on time and off
     time, and switches the normal cycle and the quick burst on and off.
       normal cycle on: run at the speed for the on time, park, wait the off time, repeat
                        (a magnet-type controller just runs continuously at the speed)
       quick burst on:  run continuously at the speed until it is switched off
     The settings are kept in flash, so the board carries on after a power cut (the burst switch is
     not kept, so the motor never starts running non-stop on its own at power-up).
   - Runs the motor at 20 kHz PWM (silent, above hearing) with smooth ramps.
   - Every stop goes via the wiper's park position when USE_PARK is set.
   - Cuts the motor if the battery drops below 10.5 V or rises above 16 V.
   - USB serial (115200) takes the same app commands, one per line (e.g. aS128, aN?bb), plus:
       s <0-100>        set speed now (manual mode)
       r <ms>           set ramp time used by 's'
       go               start / restart the built-in step program (program[] below)
       stop             stop (parking the wiper), manual mode
       v                print battery voltage, park-input voltage, duty, mode and Bluetooth state

  Park switch wiring (J5): pin 1 to the motor's park terminal, pin 2 to GND if the park contact
  switches to ground. The board pulls pin 1 up to 12 V. "Parked" is read when pin 1 is below half the
  battery voltage. This also works for car-style 31b park terminals, which switch to the motor's
  own ground (the PWM-switched side here); the final approach runs at PARK_PCT so they read clearly.

  FlightLine app protocol (from the flightline-ios / flightline-android apps)
   Every command is 5 ASCII characters starting with 'a', written without response to FFE1.
   Replies go back as notifications on FFE1.
     aT?bb          -> "ty<n>"  device type: 1 flapper, 2 magnet, 3 French flapper
     aS?bb / aN?bb / aF?bb / aB?bb / aC?bb
                    -> "sp<n>" / "on<n>" / "of<n>" / "XX<0|1>" / "xx<0|1>"
     aS###          speed 0-255
     aN###          on time, tenths of a second (the app shows n/10 + (255-n)/255 s; minimum 25)
     aF###          off time, tenths of a second
     axXXX / ayYYY  normal cycle on / off
     aXXXX / aYYYY  quick burst on / off
*/

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>

// ---------------- pins & PWM ----------------
const int PIN_PWM   = 4;
const int PIN_VSENS = 1;
const int PIN_LED   = 2;
const int PIN_POT   = 5;          // optional speed pot on J4 (3V3 - IO5 - GND)
const bool USE_POT  = false;      // set true to control speed with the pot instead of the app

const uint32_t PWM_FREQ = 20000;  // 20 kHz
const uint8_t  PWM_BITS = 10;     // 0..1023
const uint32_t PWM_MAX  = (1u << PWM_BITS) - 1;

// Motors often will not start below ~15-25 % duty. Anything non-zero below this is lifted to it.
const float MIN_RUN_PCT = 18.0f;

// ---------------- FlightLine app (Bluetooth LE) ----------------
const char    *BLE_NAME       = "Flightline";  // the apps only connect to devices with this name
const uint8_t  FL_DEVICE_TYPE = 1;      // what the app shows: 1 flapper, 2 magnet, 3 French flapper
const uint32_t APP_RAMP_MS    = 300;    // ramp for app speed changes (the app's magnet ramp steps every 300 ms)

// ---------------- wiper park switch (J5 -> IO7) ----------------
const bool  USE_PARK      = true;     // stop the blades at the park position whenever the motor stops
const int   PIN_PARK      = 7;
const float PARK_DIVIDER  = (100.0f + 10.0f) / 10.0f;   // R18 / R19
const bool  PARK_INVERT   = false;    // set true if your park contact is OPEN at the park position
const float PARK_PCT      = 70.0f;    // speed for the run to park (>= 60 % for 31b-style switches)
const uint32_t PARK_TIMEOUT_MS = 6000;  // more than one full wipe at PARK_PCT; then stop anyway

// ---------------- battery protection ----------------
const float DIVIDER   = (100.0f + 18.0f) / 18.0f;  // R13 / R14
const float V_LOW_CUT = 10.5f, V_LOW_OK = 11.5f;   // with hysteresis
const float V_HIGH_CUT = 16.0f;

// ---------------- the built-in step program (USB 'go') ----------------
struct Step { float speedPct; uint32_t rampMs; uint32_t holdMs; };

// Edit this to suit. It loops forever once started with 'go'.
Step program[] = {
  {  40, 1500, 5000 },   // ramp to 40 % over 1.5 s, run 5 s
  { 100, 2000, 8000 },   // ramp to full speed, run 8 s
  {   0, 1000, 3000 },   // ramp down, PAUSE 3 s
  {  60,  800, 4000 },
  {   0,  500, 2000 },   // pause 2 s
};
const int N_STEPS = sizeof(program) / sizeof(program[0]);

// Who is in charge of the motor: the app's settings, the step program, or manual 's' / pot control.
enum Mode : uint8_t { MODE_APP, MODE_PROGRAM, MODE_MANUAL };
const Mode START_MODE = MODE_APP;

// ---------------- state ----------------
float currentPct = 0, targetPct = 0, startPct = 0;
uint32_t rampStart = 0, rampMs = 1000, stepStart = 0;
int stepIdx = 0;
Mode mode = START_MODE;
bool faulted = false;
uint32_t manualRampMs = 1000;
bool parking = false, parkPending = false;   // parkPending: a park was cut short by a battery fault
bool parkedKnown = false;                    // stopped at the park position since the motor last ran
uint32_t parkStart = 0;
int parkHits = 0;
float lastVbat = 12.0f;

// FlightLine settings, raw 0-255 as the app sends them (defaults match the Android app's)
struct FlSettings { uint8_t speed, onTime, offTime, cycle, burst; };
FlSettings fl = { 255, 25, 60, 0, 0 };
bool flOnPhase = false;                // normal cycle: in the "on" part
uint32_t flPhaseStart = 0;
bool motorIdle = true;                 // stopped (and parked, if parking) ...
uint32_t idleSince = 0;                // ... since this time; the off time counts from here
bool flDirty = false;                  // settings to write to flash
uint32_t flChangedAt = 0;
Preferences prefs;

// Bluetooth: writes arrive on the BLE task and are handed to loop() through this buffer
BLECharacteristic *bleChr = nullptr;
volatile bool bleConnected = false;
char bleRx[128];
volatile uint16_t bleHead = 0, bleTail = 0;
portMUX_TYPE bleMux = portMUX_INITIALIZER_UNLOCKED;

void writeDuty(float pct) {
  if (pct > 0 && pct < MIN_RUN_PCT) pct = MIN_RUN_PCT;
  pct = constrain(pct, 0.0f, 100.0f);
  ledcWrite(PIN_PWM, (uint32_t)(pct * PWM_MAX / 100.0f + 0.5f));
}

void rampTo(float pct, uint32_t ms) {
  startPct = currentPct; targetPct = pct; rampMs = ms ? ms : 1; rampStart = millis();
}

float batteryVolts() {
  uint32_t mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(PIN_VSENS);
  return (mv / 16.0f) / 1000.0f * DIVIDER;
}

float parkVolts() {
  return analogReadMilliVolts(PIN_PARK) / 1000.0f * PARK_DIVIDER;
}

bool atPark() {
  bool low = parkVolts() < 0.5f * lastVbat;
  return low != PARK_INVERT;
}

void finishPark(bool found);

void beginPark() {
  parking = true; parkPending = false; parkHits = 0; parkStart = millis();
  if (currentPct <= 0 && atPark()) { finishPark(true); return; }   // contact-to-GND switch: already there
  rampTo(PARK_PCT, 300);
}

void finishPark(bool found) {
  parking = false; parkedKnown = found;
  currentPct = startPct = targetPct = 0; rampStart = millis();
  if (!found) Serial.println("PARK: park position not seen - stopped where it is (check J5 wiring)");
  if (mode == MODE_PROGRAM) stepStart = millis() - program[stepIdx].rampMs;   // pause time counts from now
}

// stop the motor: via the park position when parking is enabled
void stopMotor(uint32_t ms) {
  if (USE_PARK && parkedKnown && currentPct <= 0 && targetPct <= 0) return;   // already parked
  if (USE_PARK) beginPark();
  else { parking = false; rampTo(0, ms); }
}

void startStep(int i) {
  stepIdx = i % N_STEPS;
  stepStart = millis();
  if (program[stepIdx].speedPct <= 0) stopMotor(program[stepIdx].rampMs);
  else { parking = parkPending = false; rampTo(program[stepIdx].speedPct, program[stepIdx].rampMs); }
}

// ---------------- FlightLine settings ----------------
float appSpeedPct() {
  if (FL_DEVICE_TYPE == 3) return 100.0f;          // French flappers have no speed control
  return fl.speed * 100.0f / 255.0f;
}

uint32_t onTimeMs() {
  uint32_t n = max(fl.onTime, (uint8_t)25);        // the app never sends less than 25 (2.5 s)
  return n * 100u + (255u - n) * 1000u / 255u;     // matches the seconds the app displays
}

uint32_t offTimeMs() { return fl.offTime * 100u; }

// What the app settings ask for right now, in percent (0 = stopped / parked)
float appWant(uint32_t now) {
  if (fl.burst) return appSpeedPct();
  if (!fl.cycle) { flOnPhase = false; return 0; }
  if (FL_DEVICE_TYPE == 2) return appSpeedPct();   // magnet: runs while switched on
  if (flOnPhase) {
    if (now - flPhaseStart < onTimeMs()) return appSpeedPct();
    flOnPhase = false;                             // on time over: stop (and park)
    return 0;
  }
  if (motorIdle && now - idleSince >= offTimeMs()) {
    flOnPhase = true; flPhaseStart = now;
    return appSpeedPct();
  }
  return 0;
}

void loadSettings() {
  prefs.begin("flightline", false);
  fl.speed   = prefs.getUChar("speed", fl.speed);
  fl.onTime  = prefs.getUChar("on", fl.onTime);
  fl.offTime = prefs.getUChar("off", fl.offTime);
  fl.cycle   = prefs.getUChar("cycle", fl.cycle);
  fl.burst   = 0;                                  // never start running non-stop at power-up
  if (fl.cycle) { flOnPhase = true; flPhaseStart = millis(); }
}

void saveSettingsIfDue(uint32_t now) {
  // sliders send a stream of values while they move, so wait until they settle before writing flash
  if (!flDirty || now - flChangedAt < 2000) return;
  flDirty = false;
  prefs.putUChar("speed", fl.speed);
  prefs.putUChar("on", fl.onTime);
  prefs.putUChar("off", fl.offTime);
  prefs.putUChar("cycle", fl.cycle);
}

enum Source { FROM_USB, FROM_BLE };

void reply(Source src, const char *text) {
  if (src == FROM_BLE) {
    if (bleConnected && bleChr) { bleChr->setValue((const uint8_t *)text, strlen(text)); bleChr->notify(); }
  } else {
    Serial.println(text);
  }
}

void changed(uint8_t &field, uint8_t value) {
  field = value;
  flDirty = true; flChangedAt = millis();
  if (mode != MODE_APP) { mode = MODE_APP; parking = parkPending = false; }
}

// One 5-character app command, e.g. "aS128" or "aT?bb"
void handleAppCommand(const char *c, Source src) {
  char buf[12];
  if (!strncmp(c, "aXXXX", 5)) { changed(fl.burst, 1); return; }
  if (!strncmp(c, "aYYYY", 5)) { changed(fl.burst, 0); return; }
  if (!strncmp(c, "axXXX", 5)) {
    if (!fl.cycle) { flOnPhase = true; flPhaseStart = millis(); }   // start with an "on" period
    changed(fl.cycle, 1); return;
  }
  if (!strncmp(c, "ayYYY", 5)) { changed(fl.cycle, 0); return; }
  if (c[2] == '?') {
    switch (c[1]) {
      case 'T': snprintf(buf, sizeof buf, "ty%u", FL_DEVICE_TYPE); break;
      case 'S': snprintf(buf, sizeof buf, "sp%u", fl.speed); break;
      case 'N': snprintf(buf, sizeof buf, "on%u", fl.onTime); break;
      case 'F': snprintf(buf, sizeof buf, "of%u", fl.offTime); break;
      case 'B': snprintf(buf, sizeof buf, "XX%u", fl.burst ? 1 : 0); break;
      case 'C': snprintf(buf, sizeof buf, "xx%u", fl.cycle ? 1 : 0); break;
      default: return;
    }
    reply(src, buf);
    return;
  }
  if (!isdigit((unsigned char)c[2]) || !isdigit((unsigned char)c[3]) || !isdigit((unsigned char)c[4])) return;
  int v = (c[2] - '0') * 100 + (c[3] - '0') * 10 + (c[4] - '0');
  uint8_t value = (uint8_t)min(v, 255);
  switch (c[1]) {
    case 'S': changed(fl.speed, value); break;
    case 'N': changed(fl.onTime, value); break;
    case 'F': changed(fl.offTime, value); break;
    case 'B': changed(fl.burst, value ? 1 : 0); break;
    case 'C':
      if (value && !fl.cycle) { flOnPhase = true; flPhaseStart = millis(); }
      changed(fl.cycle, value ? 1 : 0);
      break;
  }
}

// Commands may arrive split across writes or several in one write: resync on 'a', act on 5 characters.
void feedAppBytes(char *pending, uint8_t &len, char ch, Source src) {
  if (len == 0 && ch != 'a') return;
  pending[len++] = ch;
  if (len == 5) { pending[5] = 0; handleAppCommand(pending, src); len = 0; }
}

// ---------------- Bluetooth LE ----------------
class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { bleConnected = true; }
  void onDisconnect(BLEServer *) override {
    bleConnected = false;
    BLEDevice::startAdvertising();                 // let the phone (or another one) find it again
  }
};

class SerialCharCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    String v = c->getValue();
    portENTER_CRITICAL(&bleMux);
    for (unsigned i = 0; i < v.length(); i++) {
      uint16_t next = (bleHead + 1) % sizeof(bleRx);
      if (next == bleTail) break;                  // full: drop the rest
      bleRx[bleHead] = v[i]; bleHead = next;
    }
    portEXIT_CRITICAL(&bleMux);
  }
};

void startBluetooth() {
  BLEDevice::init(BLE_NAME);
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService *service = server->createService(BLEUUID((uint16_t)0xFFE0));
  bleChr = service->createCharacteristic(BLEUUID((uint16_t)0xFFE1),
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE |
      BLECharacteristic::PROPERTY_WRITE_NR | BLECharacteristic::PROPERTY_NOTIFY);
#if !defined(CONFIG_NIMBLE_ENABLED)
  bleChr->addDescriptor(new BLE2902());            // lets Android switch notifications on (NimBLE adds it itself)
#endif
  bleChr->setCallbacks(new SerialCharCallbacks());
  service->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLEUUID((uint16_t)0xFFE0));
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}

void handleBluetooth() {
  static char pending[6];
  static uint8_t len = 0;
  while (true) {
    char ch;
    portENTER_CRITICAL(&bleMux);
    bool any = bleTail != bleHead;
    if (any) { ch = bleRx[bleTail]; bleTail = (bleTail + 1) % sizeof(bleRx); }
    portEXIT_CRITICAL(&bleMux);
    if (!any) break;
    feedAppBytes(pending, len, ch, FROM_BLE);
  }
}

// ---------------- USB serial ----------------
void handleSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\n' && c != '\r') { line += c; continue; }
    line.trim();
    if (line.startsWith("a")) {                    // FlightLine app command(s), e.g. aS128 or aT?bb
      char pending[6]; uint8_t len = 0;
      for (unsigned i = 0; i < line.length(); i++) feedAppBytes(pending, len, line[i], FROM_USB);
    }
    else if (line.startsWith("s ")) {
      mode = MODE_MANUAL;
      float pct = line.substring(2).toFloat();
      if (pct <= 0) stopMotor(manualRampMs);
      else { parking = parkPending = false; rampTo(pct, manualRampMs); }
    }
    else if (line.startsWith("r ")) { manualRampMs = line.substring(2).toInt(); }
    else if (line == "go")   { mode = MODE_PROGRAM; startStep(0); }
    else if (line == "stop") { mode = MODE_MANUAL; stopMotor(manualRampMs); }
    else if (line == "v")    {
      static const char *const MODES[] = { "app", "program", "manual" };
      Serial.printf("Vbat %.2f V, park input %.2f V (%s), duty %.1f %%, %s, mode %s, bluetooth %s\n",
                    batteryVolts(), parkVolts(), atPark() ? "at park" : "not at park", currentPct,
                    faulted ? "FAULT" : "ok", MODES[mode], bleConnected ? "connected" : "advertising");
    }
    else if (line.length())  { Serial.println("cmds: aS128 / aT?bb ... (app) | s <0-100> | r <ms> | go | stop | v"); }
    line = "";
  }
}

void setup() {
  pinMode(PIN_PWM, OUTPUT); digitalWrite(PIN_PWM, LOW);    // motor off first thing
  ledcAttach(PIN_PWM, PWM_FREQ, PWM_BITS);
  ledcWrite(PIN_PWM, 0);
  pinMode(PIN_LED, OUTPUT);
  analogSetPinAttenuation(PIN_VSENS, ADC_11db);
  if (USE_PARK) analogSetPinAttenuation(PIN_PARK, ADC_11db);
  if (USE_POT) analogSetPinAttenuation(PIN_POT, ADC_11db);
  Serial.begin(115200);
  delay(300);
  loadSettings();
  startBluetooth();
  Serial.println("motor_ctrl ready");
  if (USE_POT) { mode = MODE_MANUAL; stopMotor(300); }     // pot mode: park the blades at power-up
  else if (mode == MODE_PROGRAM) startStep(0);
}

void loop() {
  handleSerial();
  handleBluetooth();
  uint32_t now = millis();

  // battery protection
  static uint32_t lastV = 0;
  if (now - lastV > 100) {
    lastV = now;
    float v = batteryVolts();
    lastVbat = v;
    if (!faulted && (v < V_LOW_CUT || v > V_HIGH_CUT)) {
      // hold the output at 0 while faulted; targetPct is kept so manual speed can resume
      faulted = true; ledcWrite(PIN_PWM, 0); currentPct = startPct = 0;
      if (parking) { parking = false; parkPending = true; }
      Serial.printf("FAULT: battery %.2f V - motor off\n", v);
    } else if (faulted && v > V_LOW_OK && v < V_HIGH_CUT - 0.5f) {
      // resume with a ramp up from 0, never a jump straight back to the old speed
      faulted = false; Serial.println("battery ok - resuming");
      if (parkPending) beginPark();                  // finish the interrupted park
      else if (mode == MODE_PROGRAM) startStep(stepIdx);
      else rampTo(targetPct, manualRampMs);
    }
  }

  if (USE_POT) {
    // the pot sets the target; the ramp below moves to it, so turning the pot fast or recovering
    // from a fault never steps the motor straight to full speed
    mode = MODE_MANUAL;
    float want = analogRead(PIN_POT) * 100.0f / 4095.0f;
    if (want < 2.0f) {                         // bottom of the travel = off (parked)
      if (!parking && !parkPending && targetPct != 0) stopMotor(300);
    } else if (parking || fabsf(want - targetPct) > 1.0f) {
      parking = parkPending = false; rampTo(want, 300);
    }
  }

  // the app's settings drive the motor in app mode
  if (mode == MODE_APP && !faulted) {
    float want = appWant(now);
    if (want > 0) {
      if (parking || parkPending || fabsf(targetPct - want) > 0.01f) {
        parking = parkPending = false; rampTo(want, APP_RAMP_MS);
      }
    } else if (!parking && !parkPending && targetPct > 0) {
      stopMotor(APP_RAMP_MS);
    }
  }

  // parking: run at PARK_PCT until the park input reads "parked" three times in a row
  if (parking && !faulted) {
    if (currentPct >= PARK_PCT - 1.0f && atPark()) parkHits++; else parkHits = 0;
    if (parkHits >= 3) finishPark(true);
    else if (now - parkStart > PARK_TIMEOUT_MS) finishPark(false);
  }

  // program sequencing
  if (mode == MODE_PROGRAM && !faulted && !parking && !parkPending) {
    const Step &s = program[stepIdx];
    if (now - stepStart >= s.rampMs + s.holdMs) startStep(stepIdx + 1);
  }

  // ramp (frozen at 0 while faulted)
  if (!faulted) {
    float t = min(1.0f, (now - rampStart) / (float)rampMs);
    currentPct = startPct + (targetPct - startPct) * t;
  }
  if (currentPct > 0) parkedKnown = false;
  bool idle = currentPct <= 0 && targetPct <= 0 && !parking && !parkPending;
  if (idle && !motorIdle) idleSince = now;
  motorIdle = idle;
  writeDuty(faulted ? 0 : currentPct);

  saveSettingsIfDue(now);

  // LED: fast blink on fault, slow blink while running, off when stopped
  uint32_t period = faulted ? 150 : (currentPct > 0 ? 600 : 0);
  digitalWrite(PIN_LED, period ? ((now / period) & 1) : LOW);
  delay(2);
}
