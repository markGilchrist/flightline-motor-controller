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
   - Runs the motor at 20 kHz PWM (silent, above hearing) with smooth ramps.
   - Plays a looping "program" of steps: speed %, ramp time, hold time.
     A step with speed 0 is a pause. With USE_PARK the wiper first runs on to its park position, then
     pauses there (the pause time counts from when it parks).
   - Cuts the motor if the battery drops below 10.5 V or rises above 16 V.
   - Accepts commands over USB serial (115200):
       s <0-100>        set speed now (stops the program)
       r <ms>           set ramp time used by 's'
       go               start / restart the program
       stop             stop (parking the wiper) and stop the program
       v                print battery voltage, park-input voltage and current duty

  Park switch wiring (J5): pin 1 to the motor's park terminal, pin 2 to GND if the park contact
  switches to ground. The board pulls pin 1 up to 12 V. "Parked" is read when pin 1 is below half the
  battery voltage. This also works for car-style 31b park terminals, which switch to the motor's
  own ground (the PWM-switched side here); the final approach runs at PARK_PCT so they read clearly.
*/

#include <Arduino.h>

// ---------------- pins & PWM ----------------
const int PIN_PWM   = 4;
const int PIN_VSENS = 1;
const int PIN_LED   = 2;
const int PIN_POT   = 5;          // optional speed pot on J4 (3V3 - IO5 - GND)
const bool USE_POT  = false;      // set true to control speed with the pot instead of the program

const uint32_t PWM_FREQ = 20000;  // 20 kHz
const uint8_t  PWM_BITS = 10;     // 0..1023
const uint32_t PWM_MAX  = (1u << PWM_BITS) - 1;

// Motors often will not start below ~15-25 % duty. Anything non-zero below this is lifted to it.
const float MIN_RUN_PCT = 18.0f;

// ---------------- wiper park switch (J5 -> IO7) ----------------
const bool  USE_PARK      = true;     // stop the blades at the park position for pauses and 'stop'
const int   PIN_PARK      = 7;
const float PARK_DIVIDER  = (100.0f + 10.0f) / 10.0f;   // R18 / R19
const bool  PARK_INVERT   = false;    // set true if your park contact is OPEN at the park position
const float PARK_PCT      = 70.0f;    // speed for the run to park (>= 60 % for 31b-style switches)
const uint32_t PARK_TIMEOUT_MS = 6000;  // more than one full wipe at PARK_PCT; then stop anyway

// ---------------- battery protection ----------------
const float DIVIDER   = (100.0f + 18.0f) / 18.0f;  // R13 / R14
const float V_LOW_CUT = 10.5f, V_LOW_OK = 11.5f;   // with hysteresis
const float V_HIGH_CUT = 16.0f;

// ---------------- the program ----------------
struct Step { float speedPct; uint32_t rampMs; uint32_t holdMs; };

// Edit this to suit. It loops forever.
Step program[] = {
  {  40, 1500, 5000 },   // ramp to 40 % over 1.5 s, run 5 s
  { 100, 2000, 8000 },   // ramp to full speed, run 8 s
  {   0, 1000, 3000 },   // ramp down, PAUSE 3 s
  {  60,  800, 4000 },
  {   0,  500, 2000 },   // pause 2 s
};
const int N_STEPS = sizeof(program) / sizeof(program[0]);

// ---------------- state ----------------
float currentPct = 0, targetPct = 0, startPct = 0;
uint32_t rampStart = 0, rampMs = 1000, stepStart = 0;
int stepIdx = 0;
bool programRunning = true, faulted = false;
uint32_t manualRampMs = 1000;
bool parking = false, parkPending = false;   // parkPending: a park was cut short by a battery fault
bool parkedKnown = false;                    // stopped at the park position since the motor last ran
uint32_t parkStart = 0;
int parkHits = 0;
float lastVbat = 12.0f;

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
  if (programRunning) stepStart = millis() - program[stepIdx].rampMs;   // pause time counts from now
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

void handleSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\n' && c != '\r') { line += c; continue; }
    line.trim();
    if (line.startsWith("s ")) {
      programRunning = false;
      float pct = line.substring(2).toFloat();
      if (pct <= 0) stopMotor(manualRampMs);
      else { parking = parkPending = false; rampTo(pct, manualRampMs); }
    }
    else if (line.startsWith("r ")) { manualRampMs = line.substring(2).toInt(); }
    else if (line == "go")   { programRunning = true; startStep(0); }
    else if (line == "stop") { programRunning = false; stopMotor(manualRampMs); }
    else if (line == "v")    {
      Serial.printf("Vbat %.2f V, park input %.2f V (%s), duty %.1f %%, %s\n", batteryVolts(), parkVolts(),
                    atPark() ? "at park" : "not at park", currentPct, faulted ? "FAULT" : "ok");
    }
    else if (line.length())  { Serial.println("cmds: s <0-100> | r <ms> | go | stop | v"); }
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
  Serial.println("motor_ctrl ready");
  if (USE_POT) { programRunning = false; stopMotor(300); }   // pot mode: park the blades at power-up
  else startStep(0);
}

void loop() {
  handleSerial();
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
      else if (programRunning) startStep(stepIdx);
      else rampTo(targetPct, manualRampMs);
    }
  }

  if (USE_POT) {
    // the pot sets the target; the ramp below moves to it, so turning the pot fast or recovering
    // from a fault never steps the motor straight to full speed
    programRunning = false;
    float want = analogRead(PIN_POT) * 100.0f / 4095.0f;
    if (want < 2.0f) {                         // bottom of the travel = off (parked)
      if (!parking && !parkPending && targetPct != 0) stopMotor(300);
    } else if (parking || fabsf(want - targetPct) > 1.0f) {
      parking = parkPending = false; rampTo(want, 300);
    }
  }

  // parking: run at PARK_PCT until the park input reads "parked" three times in a row
  if (parking && !faulted) {
    if (currentPct >= PARK_PCT - 1.0f && atPark()) parkHits++; else parkHits = 0;
    if (parkHits >= 3) finishPark(true);
    else if (now - parkStart > PARK_TIMEOUT_MS) finishPark(false);
  }

  // program sequencing
  if (programRunning && !faulted && !parking && !parkPending) {
    const Step &s = program[stepIdx];
    if (now - stepStart >= s.rampMs + s.holdMs) startStep(stepIdx + 1);
  }

  // ramp (frozen at 0 while faulted)
  if (!faulted) {
    float t = min(1.0f, (now - rampStart) / (float)rampMs);
    currentPct = startPct + (targetPct - startPct) * t;
  }
  if (currentPct > 0) parkedKnown = false;
  writeDuty(faulted ? 0 : currentPct);

  // LED: fast blink on fault, slow blink while running, off when stopped
  uint32_t period = faulted ? 150 : (currentPct > 0 ? 600 : 0);
  digitalWrite(PIN_LED, period ? ((now / period) & 1) : LOW);
  delay(2);
}
