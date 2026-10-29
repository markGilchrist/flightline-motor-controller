// Host-side tests for motor_pwm.ino: builds the real sketch against mock/Arduino.h and runs it in
// simulated time.  Build and run:  sh firmware/test/run_tests.sh
// Test sets (chosen by run_tests.sh): default = program, battery and serial behaviour (USE_PARK off),
// POT_TEST = speed pot, PARK_TEST = wiper parking with a model of the motor and its park switch,
// APP_TEST = the FlightLine app protocol over Bluetooth (the test plays the phone).
#include "Arduino.h"
#include "BLEDevice.h"
#include "Preferences.h"

uint32_t sim_ms = 0;
float sim_vbat = 12.6f, sim_pot_frac = 0;
uint32_t sim_duty[64];
int sim_attached[64], sim_level[64];
std::string sim_serial_in, sim_serial_out;
SerialMock Serial;
uint32_t (*sim_adc_hook)(uint8_t pin) = nullptr;
std::vector<std::string> sim_ble_notified;
SimBle sim_ble;
std::map<std::string, uint8_t> sim_flash;
int sim_flash_writes = 0;

#ifndef SKETCH
#define SKETCH "../motor_pwm/motor_pwm.ino"
#endif
#include SKETCH

static int failures = 0;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; std::printf("  FAIL line %d: ", __LINE__); \
  std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

static float duty() { return sim_duty[PIN_PWM] * 100.0f / PWM_MAX; }

// ---- wiper motor + park switch model ----
// Crank turns 300 deg/s at 100 % duty (50 rpm). The park contact is "made" for 15 deg of crank angle.
// park_type: 0 = J5 not wired, 1 = contact to GND at park, 2 = car-style 31b (switches to the motor's
// own ground = MOTOR_N, the PWM-switched node), 3 = contact to GND that OPENS at park.
static double wiper_deg = 100;
static int park_type = 1;
static double park_filt = 0;                      // voltage on C18 x 11 (i.e. referred to J5.1)
static bool at_park_window() { return std::fmod(wiper_deg, 360.0) < 15.0; }
static double park_pin_volts() {
  double pull = sim_vbat * 110.0 / 114.7;         // R17 4k7 into R18 + R19 = 110k
  double d = duty() / 100.0;
  bool in = at_park_window();
  switch (park_type) {
    case 1: return in ? 0 : pull;
    case 2: return in ? (d > 0 ? (1 - d) * (sim_vbat + 0.5) : sim_vbat) : pull;   // MOTOR_N averaged by C18
    case 3: return in ? pull : 0;
    default: return pull;
  }
}
static uint32_t adc_hook(uint8_t pin) {
  if (pin != PIN_PARK) return 0;
  double mv = park_filt / 11.0 * 1000.0;
  return (uint32_t)std::lround(std::min(std::max(mv, 0.0), 3100.0));
}

// Run loop() until time t. Tracks the largest upward step in duty: the only allowed jump is the
// minimum-run kick from 0 to MIN_RUN_PCT; anything else must ramp.
static float worst_jump = 0;
static uint32_t worst_jump_at = 0;
static bool below_min_seen = false;
static void run_until(uint32_t t) {
  while (sim_ms < t) {
    float before = duty();
    uint32_t t_before = sim_ms;
    loop();
    float after = duty(), step = after - before;
    if (before == 0 && after <= MIN_RUN_PCT + 0.2f) step = 0;      // the start kick
    if (step > worst_jump) { worst_jump = step; worst_jump_at = sim_ms; }
    if (after > 0 && after < MIN_RUN_PCT - 0.2f) below_min_seen = true;
    double dt = sim_ms - t_before;
    wiper_deg += 300.0 * after / 100.0 * dt / 1000.0;
    park_filt += (park_pin_volts() - park_filt) * (1 - std::exp(-dt / 4.3));  // R18||R19 x C18
  }
}
// keep_flash = false: a new board; true: a reboot that keeps the saved settings
static void reset_sim(float vbat, bool keep_flash = false) {
  sim_ms = 0; sim_vbat = vbat; sim_serial_in.clear(); sim_serial_out.clear();
  for (auto &d : sim_duty) d = 0;
  for (auto &a : sim_attached) a = 0;
  if (!keep_flash) sim_flash.clear();
  sim_ble_notified.clear(); sim_flash_writes = 0;
  currentPct = targetPct = startPct = 0; rampStart = stepStart = 0; rampMs = 1000;
  stepIdx = 0; mode = START_MODE; faulted = false; manualRampMs = 1000;
  fl = FlSettings{ 255, 25, 60, 0, 0 }; flOnPhase = false; flPhaseStart = 0;
  motorIdle = true; idleSince = 0; flDirty = false; bleConnected = false; bleHead = bleTail = 0;
  parking = parkPending = parkedKnown = false; parkHits = 0; lastVbat = 12.0f;
  worst_jump = 0; below_min_seen = false;
  sim_adc_hook = adc_hook; park_filt = park_pin_volts();
  setup();
}
[[maybe_unused]] static void send(const char *line) { sim_serial_in += line; sim_serial_in += "\n"; }
// run until the motor output is 0, at most `limit` ms; returns the time it took
[[maybe_unused]] static uint32_t run_until_stopped(uint32_t limit) {
  uint32_t t0 = sim_ms;
  while (duty() != 0 && sim_ms - t0 < limit) run_until(sim_ms + 2);
  return sim_ms - t0;
}

#if defined(APP_TEST) || defined(MAGNET_TEST)
// The app's reply parser (ControllerMessage in flightline-ios / ControllerMessage.parse on Android):
// tags are checked in this order with "contains", the tag is removed and the rest parsed as a number.
[[maybe_unused]] static bool app_parse(const std::string &raw, std::string &tag, int &value) {
  for (const char *t : { "ty", "xx", "XX", "on", "of", "sp" }) {
    size_t at = raw.find(t);
    if (at == std::string::npos) continue;
    std::string rest = raw; rest.erase(at, 2);
    char *end = nullptr; long v = std::strtol(rest.c_str(), &end, 10);
    if (rest.empty() || *end != 0 || v < 0 || v > 255) return false;
    tag = t; value = (int)v; return true;
  }
  return false;
}
// write one command and return the notification it produced ("" if none)
[[maybe_unused]] static std::string ask(const char *cmd) {
  size_t n = sim_ble_notified.size();
  sim_ble_write(cmd); run_until(sim_ms + 20);
  return sim_ble_notified.size() > n ? sim_ble_notified.back() : "";
}
[[maybe_unused]] static void expect_reply(const char *cmd, const char *tag, int value) {
  std::string r = ask(cmd), t; int v = -1;
  CHECK(app_parse(r, t, v) && t == tag && v == value, "%s -> '%s' (app reads tag '%s' value %d, wanted %s %d)",
        cmd, r.c_str(), t.c_str(), v, tag, value);
}
// what the app sends right after identifying a flapper (ControllerSession.writeAllSettings)
[[maybe_unused]] static void app_write_all(int speed, int on, int off, bool burst, bool cycle) {
  char b[8];
  std::snprintf(b, sizeof b, "aF%03d", off); sim_ble_write(b);
  sim_ble_write(burst ? "aXXXX" : "aYYYY");
  std::snprintf(b, sizeof b, "aN%03d", on); sim_ble_write(b);
  sim_ble_write(cycle ? "axXXX" : "ayYYY");
  std::snprintf(b, sizeof b, "aS%03d", speed); sim_ble_write(b);
}
[[maybe_unused]] static float pct(int raw) { return raw * 100.0f / 255.0f; }
#endif

#if defined(APP_TEST)
int main() {
  std::printf("Bluetooth setup matches what the apps look for\n");
  park_type = 1; wiper_deg = 100; reset_sim(12.6f);
  CHECK(sim_ble.name == "Flightline", "advertised name '%s'", sim_ble.name.c_str());
  BLECharacteristic *c = sim_ble_find(0xFFE0, 0xFFE1);
  CHECK(c != nullptr, "service FFE0 with characteristic FFE1");
  if (!c) { std::printf("\n%d FAILED\n", failures); return 1; }
  CHECK((c->props & BLECharacteristic::PROPERTY_WRITE_NR) && (c->props & BLECharacteristic::PROPERTY_NOTIFY),
        "FFE1 takes writes without response and notifies (props %u)", c->props);
  bool has2902 = false; for (auto *d : c->descriptors) has2902 |= d->uuid == 0x2902;
  CHECK(has2902, "FFE1 has the 2902 descriptor Android writes to enable notifications");
  CHECK(sim_ble.adv.uuids.size() == 1 && sim_ble.adv.uuids[0] == 0xFFE0 && sim_ble.advertisingStarts == 1,
        "advertising FFE0");
  run_until(sim_ms + 2000);
  CHECK(duty() == 0 && mode == MODE_APP, "a new board waits in app mode with the motor off: %.1f", duty());

  std::printf("handshake as the app does it\n");
  sim_ble_connect();
  expect_reply("aT?bb", "ty", 1);
  app_write_all(128, 50, 30, false, false);
  run_until(sim_ms + 500);
  CHECK(duty() == 0, "settings alone don't start the motor: %.1f", duty());
  expect_reply("aS?bb", "sp", 128);
  expect_reply("aN?bb", "on", 50);
  expect_reply("aF?bb", "of", 30);
  expect_reply("aB?bb", "XX", 0);
  expect_reply("aC?bb", "xx", 0);

  std::printf("normal cycle: on time, park, off time, repeat\n");
  uint32_t on_ms = 50 * 100 + (255 - 50) * 1000 / 255;      // 5.8 s
  sim_ble_write("axXXX");
  run_until(sim_ms + 400);
  CHECK(std::fabs(duty() - pct(128)) < 0.5f, "cycle on: runs at speed 128 = %.1f %%: %.1f", pct(128), duty());
  uint32_t t_on = sim_ms - 400;
  run_until(t_on + on_ms - 100);
  CHECK(std::fabs(duty() - pct(128)) < 0.5f, "still running near the end of the on time: %.1f", duty());
  uint32_t took = run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window(), "parks after the on time (%u ms after it ended), at %.0f deg",
        took + 100, std::fmod(wiper_deg, 360.0));
  uint32_t t_off = sim_ms;
  run_until(t_off + 2900);
  CHECK(duty() == 0, "off for the 3 s off time: %.1f", duty());
  run_until(t_off + 3400);
  CHECK(duty() > 0, "next on period starts after the off time: %.1f", duty());
  CHECK(!below_min_seen && worst_jump < 1.0f, "ramps only (jump %.1f %% at %u ms)", worst_jump, worst_jump_at);

  std::printf("speed slider while running\n");
  sim_ble_write("aS255"); run_until(sim_ms + 400);
  CHECK(duty() > 99, "speed 255: %.1f", duty());

  std::printf("cycle off parks and stays off\n");
  sim_ble_write("ayYYY"); run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window(), "cycle off: parked at %.0f deg", std::fmod(wiper_deg, 360.0));
  run_until(sim_ms + 15000); CHECK(duty() == 0, "stays off: %.1f", duty());

  std::printf("quick burst\n");
  sim_ble_write("aS200"); sim_ble_write("aXXXX"); run_until(sim_ms + 400);
  CHECK(std::fabs(duty() - pct(200)) < 0.5f, "burst runs at the speed: %.1f", duty());
  run_until(sim_ms + 20000);
  CHECK(std::fabs(duty() - pct(200)) < 0.5f, "burst keeps running past the on time: %.1f", duty());
  expect_reply("aB?bb", "XX", 1);
  sim_ble_write("aYYYY"); run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window(), "burst off parks: at %.0f deg", std::fmod(wiper_deg, 360.0));

  std::printf("split and joined writes\n");
  sim_ble_write("aS1"); sim_ble_write("00"); run_until(sim_ms + 20);
  expect_reply("aS?bb", "sp", 100);
  sim_ble_write("aN040aF010"); run_until(sim_ms + 20);
  expect_reply("aN?bb", "on", 40);
  expect_reply("aF?bb", "of", 10);
  sim_ble_write("aS999"); run_until(sim_ms + 20);
  expect_reply("aS?bb", "sp", 255);
  sim_ble_write("junk"); sim_ble_write("aQ?bb"); run_until(sim_ms + 20);
  expect_reply("aT?bb", "ty", 1);

  std::printf("settings survive a power cut (burst does not)\n");
  sim_ble_write("axXXX"); sim_ble_write("aXXXX"); run_until(sim_ms + 3000);
  CHECK(sim_flash_writes > 0, "settings written to flash");
  int writes = sim_flash_writes;
  for (int i = 0; i < 50; i++) { char b[8]; std::snprintf(b, sizeof b, "aS%03d", 100 + i); sim_ble_write(b); run_until(sim_ms + 20); }
  run_until(sim_ms + 2500);
  CHECK(sim_flash_writes - writes <= 4, "a moving slider is saved once it settles (%d writes)", sim_flash_writes - writes);
  reset_sim(12.6f, true);
  sim_ble_connect();
  expect_reply("aS?bb", "sp", 149);
  expect_reply("aN?bb", "on", 40);
  expect_reply("aF?bb", "of", 10);
  expect_reply("aC?bb", "xx", 1);
  expect_reply("aB?bb", "XX", 0);
  run_until(sim_ms + 400);
  CHECK(duty() > 0, "cycle carries on after the power cut: %.1f", duty());
  sim_ble_write("ayYYY"); run_until_stopped(3000);

  std::printf("battery fault during the cycle\n");
  sim_ble_write("axXXX"); run_until(sim_ms + 1000);
  sim_vbat = 10.0f; run_until(sim_ms + 150);
  CHECK(faulted && duty() == 0, "fault stops the motor");
  worst_jump = 0;
  sim_vbat = 12.5f; run_until(sim_ms + 150);
  CHECK(duty() < 25, "ramps back from 0 after the fault: %.1f", duty());
  CHECK(worst_jump < 1.0f, "no jump (%.1f %%)", worst_jump);
  sim_ble_write("ayYYY"); run_until_stopped(3000);

  std::printf("USB serial speaks the same commands; 'go' and the app hand over cleanly\n");
  sim_serial_out.clear(); send("aT?bb"); run_until(sim_ms + 20);
  CHECK(sim_serial_out.find("ty1") != std::string::npos, "USB aT?bb -> '%s'", sim_serial_out.c_str());
  send("go"); run_until(sim_ms + 3000);
  CHECK(mode == MODE_PROGRAM && std::fabs(duty() - 40) < 0.5f, "'go' runs the step program: %.1f", duty());
  sim_ble_write("ayYYY"); run_until_stopped(3000);
  CHECK(mode == MODE_APP && duty() == 0, "an app command takes over again: mode %d duty %.1f", mode, duty());

  std::printf("disconnect\n");
  sim_ble_disconnect(); run_until(sim_ms + 20);
  CHECK(sim_ble.advertisingStarts == 2 && !bleConnected, "advertises again after the phone disconnects");
  size_t n = sim_ble_notified.size(); sim_ble_write("aT?bb"); run_until(sim_ms + 20);
  CHECK(sim_ble_notified.size() == n, "no notifications while disconnected");

  std::printf(failures ? "\n%d FAILED\n" : "\nALL PASSED\n", failures);
  return failures ? 1 : 0;
}

#elif defined(MAGNET_TEST)
// built with FL_DEVICE_TYPE = 2: the app's magnet card (on/off with its own speed ramp)
int main() {
  std::printf("magnet controller\n");
  park_type = 1; wiper_deg = 100; reset_sim(12.6f);
  sim_ble_connect();
  { std::string r = ask("aT?bb"); CHECK(r == "ty2", "type reply '%s'", r.c_str()); }
  sim_ble_write("ayYYY"); sim_ble_write("aS120"); run_until(sim_ms + 200);
  // MagnetViewModel.setOn(true): cycle on, then speed steps down from 255 by 30 every 300 ms to the target
  sim_ble_write("axXXX");
  for (int v = 225; v > 120; v -= 30) { run_until(sim_ms + 300); char b[8]; std::snprintf(b, sizeof b, "aS%03d", v); sim_ble_write(b); }
  run_until(sim_ms + 300); sim_ble_write("aS120");
  run_until(sim_ms + 400);
  CHECK(std::fabs(duty() - pct(120)) < 0.5f, "settles at the chosen speed: %.1f", duty());
  run_until(sim_ms + 60000);
  CHECK(std::fabs(duty() - pct(120)) < 0.5f, "magnet runs continuously (no on/off times): %.1f", duty());
  // setOn(false): speed steps down to 0, then cycle off
  for (int v = 90; v >= 0; v -= 30) { run_until(sim_ms + 300); char b[8]; std::snprintf(b, sizeof b, "aS%03d", v); sim_ble_write(b); }
  run_until(sim_ms + 300); sim_ble_write("ayYYY");
  run_until_stopped(3000);
  CHECK(duty() == 0, "off after the app's ramp down: %.1f", duty());
  CHECK(worst_jump < 1.0f && !below_min_seen, "ramps only (jump %.1f %%)", worst_jump);
  std::printf(failures ? "\n%d FAILED\n" : "\nALL PASSED\n", failures);
  return failures ? 1 : 0;
}

#elif defined(POT_TEST)
// built from a copy of the sketch with USE_POT = true (parking stays on, as shipped)
int main() {
  std::printf("speed pot (USE_POT = true)\n");
  park_type = 1; wiper_deg = 100; sim_pot_frac = 0.0f; reset_sim(12.6f);
  run_until(sim_ms + 3000);
  CHECK(duty() == 0 && !(mode == MODE_PROGRAM) && at_park_window(),
        "pot at zero at power-up: blades park, then off (duty %.1f, %.0f deg)", duty(), std::fmod(wiper_deg, 360.0));
  sim_pot_frac = 0.75f; run_until(sim_ms + 100);
  CHECK(duty() < 75, "pot turned fast: output ramps, not a step (%.1f)", duty());
  run_until(sim_ms + 400); CHECK(std::fabs(duty() - 75) < 1, "follows pot to 75 %%: %.1f", duty());
  sim_pot_frac = 0.01f; run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window(), "bottom of travel parks then stops: duty %.1f, wiper at %.0f deg",
        duty(), std::fmod(wiper_deg, 360.0));
  run_until(sim_ms + 2000); CHECK(duty() == 0, "stays parked: %.1f", duty());
  sim_pot_frac = 1.0f; run_until(sim_ms + 500); CHECK(duty() > 99, "full: %.1f", duty());
  sim_vbat = 10.0f; run_until(sim_ms + 150); CHECK(faulted && duty() == 0, "fault cuts pot mode");
  worst_jump = 0;
  sim_vbat = 12.5f; run_until(sim_ms + 120);
  CHECK(duty() < 50, "pot mode restart ramps from 0, got %.1f %%", duty());
  run_until(sim_ms + 1000); CHECK(duty() > 99, "back to pot setting after the 1 s restart ramp: %.1f", duty());
  CHECK(worst_jump < 2.0f, "duty jumped up %.1f %% at %u ms", worst_jump, worst_jump_at);
  CHECK(!below_min_seen, "duty between 0 and MIN_RUN_PCT was output");
  std::printf(failures ? "\n%d FAILED\n" : "\nALL PASSED\n", failures);
  return failures ? 1 : 0;
}

#elif defined(PARK_TEST)
// the sketch as shipped (USE_PARK = true); INVERT_TEST builds it with PARK_INVERT = true
static void pause_parks(int type, const char *name) {
  std::printf("program pause parks the blades: %s\n", name);
  park_type = type; wiper_deg = 100; reset_sim(12.6f);
  uint32_t t0 = sim_ms;
  run_until(t0 + 16500);                                    // step 2 (pause) starts at 1.5+5+2+8 s
  uint32_t took = run_until_stopped(PARK_TIMEOUT_MS + 500);
  CHECK(duty() == 0, "%s: motor stops for the pause", name);
  CHECK(at_park_window(), "%s: stopped in the park window, wiper at %.0f deg", name, std::fmod(wiper_deg, 360.0));
  CHECK(took < 2500, "%s: parking took %u ms", name, took);
  CHECK(sim_serial_out.find("PARK:") == std::string::npos, "%s: no park warning: %s", name, sim_serial_out.c_str());
  double parked_at = wiper_deg;
  run_until(sim_ms + 2900);
  CHECK(duty() == 0 && wiper_deg == parked_at, "%s: holds the full 3 s pause at park", name);
  run_until(sim_ms + 400);
  CHECK(duty() > 0, "%s: next step starts after the pause: %.1f", name, duty());
  CHECK(!below_min_seen, "%s: duty between 0 and MIN_RUN_PCT was output", name);
  CHECK(worst_jump < 1.0f, "%s: duty jumped up %.1f %% at %u ms", name, worst_jump, worst_jump_at);
}

int main() {
#ifndef INVERT_TEST
  pause_parks(1, "contact to GND");
  pause_parks(2, "car-style 31b");

  std::printf("park switch not wired: gives up after the timeout\n");
  park_type = 0; reset_sim(12.6f);
  run_until(sim_ms + 16500);
  run_until(sim_ms + 3000);
  CHECK(std::fabs(duty() - PARK_PCT) < 1, "still searching for park at PARK_PCT: %.1f", duty());
  uint32_t took = run_until_stopped(PARK_TIMEOUT_MS + 500);
  CHECK(duty() == 0, "stops after the timeout");
  CHECK(took > PARK_TIMEOUT_MS - 3500 && took < PARK_TIMEOUT_MS, "timeout after %u + 3000 ms", took);
  CHECK(sim_serial_out.find("PARK: park position not seen") != std::string::npos, "warning printed");

  std::printf("'stop' and 's 0' park the blades\n");
  park_type = 1; wiper_deg = 100; reset_sim(12.6f);
  run_until(sim_ms + 9000);                                  // running at 100 %
  send("stop"); run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window() && !(mode == MODE_PROGRAM), "stop parks: duty %.1f at %.0f deg", duty(), std::fmod(wiper_deg, 360.0));
  run_until(sim_ms + 10000); CHECK(duty() == 0, "stays stopped");
  send("stop"); run_until(sim_ms + 500);
  CHECK(duty() == 0, "'stop' when already parked does not move the wiper: %.1f", duty());
  send("s 50"); run_until(sim_ms + 1500); CHECK(std::fabs(duty() - 50) < 0.5f, "s 50: %.1f", duty());
  send("s 0"); run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window(), "s 0 parks: at %.0f deg", std::fmod(wiper_deg, 360.0));

  std::printf("31b switch: 'stop' while already parked and stopped\n");
  park_type = 2; reset_sim(12.6f);
  run_until(sim_ms + 3000); send("stop"); run_until_stopped(3000);
  CHECK(at_park_window(), "parked first");
  double where = wiper_deg;
  send("stop"); run_until(sim_ms + 3000);
  CHECK(duty() == 0 && wiper_deg == where, "no extra wipe when already parked");

  std::printf("battery fault while parking\n");
  park_type = 2; wiper_deg = 100; reset_sim(12.6f);
  run_until(sim_ms + 9000);
  wiper_deg = 20;                                            // just past park: a full turn to go
  send("stop"); run_until(sim_ms + 200);
  CHECK(parking, "parking under way");
  sim_vbat = 10.0f; run_until(sim_ms + 150);
  CHECK(faulted && duty() == 0, "fault stops the motor mid-park");
  run_until(sim_ms + 1000);
  worst_jump = 0;
  sim_vbat = 12.5f; run_until(sim_ms + 150);
  CHECK(!faulted && parking, "parking resumes after the fault");
  run_until_stopped(3000);
  CHECK(duty() == 0 && at_park_window(), "finishes at park: %.0f deg", std::fmod(wiper_deg, 360.0));
  CHECK(worst_jump < 1.0f, "duty jumped up %.1f %% at %u ms", worst_jump, worst_jump_at);

  std::printf("v reports the park input\n");
  sim_serial_out.clear(); send("v"); run_until(sim_ms + 10);
  CHECK(sim_serial_out.find("park input") != std::string::npos && sim_serial_out.find("at park") != std::string::npos,
        "v output: %s", sim_serial_out.c_str());
#else
  pause_parks(3, "contact that opens at park (PARK_INVERT = true)");
#endif
  std::printf(failures ? "\n%d FAILED\n" : "\nALL PASSED\n", failures);
  return failures ? 1 : 0;
}

#else
// built from a copy of the sketch with USE_PARK = false: plain stop/pause behaviour
int main() {
  std::printf("program sequence\n");
  reset_sim(12.6f);
  CHECK(sim_attached[PIN_PWM] == 10, "PWM pin attached with %d bits", sim_attached[PIN_PWM]);
  uint32_t t0 = sim_ms;                                   // setup() took 300 ms
  run_until(t0 + 750);   CHECK(std::fabs(duty() - 20) < 2.5f, "mid ramp to 40 %%: %.1f", duty());
  run_until(t0 + 3000);  CHECK(std::fabs(duty() - 40) < 0.5f, "holding 40 %%: %.1f", duty());
  run_until(t0 + 6500 + 2100); CHECK(duty() > 99.5f, "full speed: %.1f", duty());
  run_until(t0 + 6500 + 10000 + 1100); CHECK(duty() == 0, "first pause: %.1f", duty());
  run_until(t0 + 6500 + 10000 + 3900); CHECK(duty() == 0, "still paused: %.1f", duty());
  run_until(t0 + 6500 + 10000 + 4000 + 4800 + 600); CHECK(duty() == 0, "second pause: %.1f", duty());
  run_until(t0 + 26800 + 2500 + 1600); CHECK(std::fabs(duty() - 40) < 1, "program looped: %.1f", duty());
  CHECK(!below_min_seen, "duty between 0 and MIN_RUN_PCT was output");
  CHECK(worst_jump < 1.0f, "duty jumped up %.1f %% at %u ms", worst_jump, worst_jump_at);

  std::printf("low battery cut-out and recovery\n");
  reset_sim(12.6f);
  run_until(sim_ms + 9000);                                // well into the 100 % step
  CHECK(duty() > 99, "running at full speed before the fault: %.1f", duty());
  sim_vbat = 10.2f; run_until(sim_ms + 120);
  CHECK(faulted && duty() == 0, "cut below 10.5 V: faulted=%d duty=%.1f", faulted, duty());
  sim_vbat = 11.2f; run_until(sim_ms + 3000);
  CHECK(faulted && duty() == 0, "stays off inside the hysteresis band: duty=%.1f", duty());
  worst_jump = 0;
  sim_vbat = 12.4f; run_until(sim_ms + 120);
  CHECK(!faulted, "resumes above 11.5 V");
  CHECK(duty() < 25, "restart must ramp from 0, duty right after resume is %.1f %%", duty());
  run_until(sim_ms + 3000);
  CHECK(duty() > 99, "back to full speed after the ramp: %.1f", duty());
  CHECK(worst_jump < 1.0f, "duty jumped up %.1f %% at %u ms after recovery", worst_jump, worst_jump_at);

  std::printf("over-voltage cut-out\n");
  reset_sim(12.6f);
  run_until(sim_ms + 3000);
  sim_vbat = 16.5f; run_until(sim_ms + 120);
  CHECK(faulted && duty() == 0, "cut above 16 V: faulted=%d duty=%.1f", faulted, duty());
  sim_vbat = 15.7f; run_until(sim_ms + 500);
  CHECK(faulted, "stays off until below 15.5 V");
  sim_vbat = 14.4f; run_until(sim_ms + 120);
  CHECK(!faulted, "resumes at 14.4 V (charging voltage)");

  std::printf("serial commands\n");
  reset_sim(12.6f);
  run_until(sim_ms + 200);
  send("r 500"); send("s 70"); run_until(sim_ms + 250);
  CHECK(!(mode == MODE_PROGRAM) && manualRampMs == 500, "s/r parsed: running=%d ramp=%u", (mode == MODE_PROGRAM), manualRampMs);
  run_until(sim_ms + 600); CHECK(std::fabs(duty() - 70) < 0.5f, "manual 70 %%: %.1f", duty());
  run_until(sim_ms + 20000); CHECK(std::fabs(duty() - 70) < 0.5f, "program stays stopped: %.1f", duty());
  sim_serial_out.clear(); send("v"); run_until(sim_ms + 10);
  CHECK(sim_serial_out.find("Vbat 12.6") != std::string::npos, "v prints voltage: '%s'", sim_serial_out.c_str());
  send("stop"); run_until(sim_ms + 1100); CHECK(duty() == 0, "stop ramps to 0: %.1f", duty());
  send("go"); run_until(sim_ms + 3500); CHECK(std::fabs(duty() - 40) < 0.5f, "go restarts program: %.1f", duty());
  sim_serial_out.clear(); send("bogus"); run_until(sim_ms + 10);
  CHECK(sim_serial_out.find("cmds:") != std::string::npos, "unknown command prints help");
  // manual speed survives a low-battery fault and ramps back from 0
  send("s 80"); run_until(sim_ms + 1500);
  sim_vbat = 10.0f; run_until(sim_ms + 150);
  worst_jump = 0;
  sim_vbat = 12.5f; run_until(sim_ms + 120);
  CHECK(duty() < 25, "manual restart after fault must ramp from 0, got %.1f %%", duty());
  run_until(sim_ms + 1500); CHECK(std::fabs(duty() - 80) < 0.5f, "manual speed restored: %.1f", duty());
  CHECK(worst_jump < 1.0f, "duty jumped up %.1f %% at %u ms", worst_jump, worst_jump_at);

  std::printf("USB power only (no battery)\n");
  reset_sim(0.0f);
  run_until(sim_ms + 2000);
  CHECK(faulted && duty() == 0, "motor stays off on USB power: faulted=%d duty=%.1f", faulted, duty());

  std::printf(failures ? "\n%d FAILED\n" : "\nALL PASSED\n", failures);
  return failures ? 1 : 0;
}
#endif
