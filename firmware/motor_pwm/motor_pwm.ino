/*
  ESP32-S3 12 V motor PWM controller  -  firmware for the "motor_ctrl" PCB
  ------------------------------------------------------------------------
  Board:   ESP32S3 Dev Module (Arduino-ESP32 core 3.x)
           Tools > USB CDC On Boot: Enabled   (so Serial works over the USB-C port)
  Pins:    GPIO4  -> PWM to UCC27517 gate driver -> IPD90N04S4L-04 low-side MOSFET
           GPIO1  -> battery sense (100k / 18k divider)
           GPIO2  -> status LED
           GPIO5, GPIO6 -> spare (AUX header J4). GPIO5 can take a 10k speed pot.

  What it does
   - Runs the motor at 20 kHz PWM (silent, above hearing) with smooth ramps.
   - Plays a looping "program" of steps: speed %, ramp time, hold time.
     A step with speed 0 is a pause.
   - Cuts the motor if the battery drops below 10.5 V or rises above 16 V.
   - Accepts commands over USB serial (115200):
       s <0-100>        set speed now (stops the program)
       r <ms>           set ramp time used by 's'
       go               start / restart the program
       stop             ramp to zero and stop the program
       v                print battery voltage and current duty
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

void startStep(int i) {
  stepIdx = i % N_STEPS;
  rampTo(program[stepIdx].speedPct, program[stepIdx].rampMs);
  stepStart = millis();
}

void handleSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\n' && c != '\r') { line += c; continue; }
    line.trim();
    if (line.startsWith("s ")) { programRunning = false; rampTo(line.substring(2).toFloat(), manualRampMs); }
    else if (line.startsWith("r ")) { manualRampMs = line.substring(2).toInt(); }
    else if (line == "go")   { programRunning = true; startStep(0); }
    else if (line == "stop") { programRunning = false; rampTo(0, manualRampMs); }
    else if (line == "v")    { Serial.printf("Vbat %.2f V, duty %.1f %%, %s\n", batteryVolts(), currentPct, faulted ? "FAULT" : "ok"); }
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
  if (USE_POT) analogSetPinAttenuation(PIN_POT, ADC_11db);
  Serial.begin(115200);
  delay(300);
  Serial.println("motor_ctrl ready");
  startStep(0);
}

void loop() {
  handleSerial();
  uint32_t now = millis();

  // battery protection
  static uint32_t lastV = 0;
  if (now - lastV > 100) {
    lastV = now;
    float v = batteryVolts();
    if (!faulted && (v < V_LOW_CUT || v > V_HIGH_CUT)) {
      faulted = true; ledcWrite(PIN_PWM, 0); currentPct = 0;
      Serial.printf("FAULT: battery %.2f V - motor off\n", v);
    } else if (faulted && v > V_LOW_OK && v < V_HIGH_CUT - 0.5f) {
      faulted = false; Serial.println("battery ok - resuming"); if (programRunning) startStep(stepIdx);
    }
  }

  if (USE_POT) { programRunning = false; targetPct = startPct = currentPct = analogRead(PIN_POT) * 100.0f / 4095.0f; }

  // program sequencing
  if (programRunning && !faulted) {
    const Step &s = program[stepIdx];
    if (now - stepStart >= s.rampMs + s.holdMs) startStep(stepIdx + 1);
  }

  // ramp
  if (!USE_POT) {
    float t = min(1.0f, (now - rampStart) / (float)rampMs);
    currentPct = startPct + (targetPct - startPct) * t;
  }
  writeDuty(faulted ? 0 : currentPct);

  // LED: fast blink on fault, slow blink while running, off when stopped
  uint32_t period = faulted ? 150 : (currentPct > 0 ? 600 : 0);
  digitalWrite(PIN_LED, period ? ((now / period) & 1) : LOW);
  delay(2);
}
