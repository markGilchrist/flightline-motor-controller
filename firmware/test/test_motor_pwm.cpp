// Host-side tests for motor_pwm.ino: builds the real sketch against mock/Arduino.h and runs it in
// simulated time.  Build and run:  sh firmware/test/run_tests.sh
// Test sets (chosen by run_tests.sh): default = program, battery and serial behaviour (USE_PARK off),
// POT_TEST = speed pot, PARK_TEST = wiper parking with a model of the motor and its park switch.
#include "Arduino.h"

uint32_t sim_ms = 0;
float sim_vbat = 12.6f, sim_pot_frac = 0;
uint32_t sim_duty[64];
int sim_attached[64], sim_level[64];
std::string sim_serial_in, sim_serial_out;
SerialMock Serial;
uint32_t (*sim_adc_hook)(uint8_t pin) = nullptr;

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
static void reset_sim(float vbat) {
  sim_ms = 0; sim_vbat = vbat; sim_serial_in.clear(); sim_serial_out.clear();
  for (auto &d : sim_duty) d = 0;
  for (auto &a : sim_attached) a = 0;
  currentPct = targetPct = startPct = 0; rampStart = stepStart = 0; rampMs = 1000;
  stepIdx = 0; programRunning = true; faulted = false; manualRampMs = 1000;
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

#if defined(POT_TEST)
// built from a copy of the sketch with USE_POT = true (parking stays on, as shipped)
int main() {
  std::printf("speed pot (USE_POT = true)\n");
  park_type = 1; wiper_deg = 100; sim_pot_frac = 0.0f; reset_sim(12.6f);
  run_until(sim_ms + 3000);
  CHECK(duty() == 0 && !programRunning && at_park_window(),
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
  CHECK(duty() == 0 && at_park_window() && !programRunning, "stop parks: duty %.1f at %.0f deg", duty(), std::fmod(wiper_deg, 360.0));
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
  CHECK(!programRunning && manualRampMs == 500, "s/r parsed: running=%d ramp=%u", programRunning, manualRampMs);
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
