// Host-side tests for motor_pwm.ino: builds the real sketch against mock/Arduino.h and runs it in
// simulated time.  Build and run:  sh firmware/test/run_tests.sh
#include "Arduino.h"

uint32_t sim_ms = 0;
float sim_vbat = 12.6f, sim_pot_frac = 0;
uint32_t sim_duty[64];
int sim_attached[64], sim_level[64];
std::string sim_serial_in, sim_serial_out;
SerialMock Serial;

#ifndef SKETCH
#define SKETCH "../motor_pwm/motor_pwm.ino"
#endif
#include SKETCH

static int failures = 0;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; std::printf("  FAIL line %d: ", __LINE__); \
  std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

static float duty() { return sim_duty[PIN_PWM] * 100.0f / PWM_MAX; }

// Run loop() until time t. Tracks the largest upward step in duty: the only allowed jump is the
// minimum-run kick from 0 to MIN_RUN_PCT; anything else must ramp.
static float worst_jump = 0;
static uint32_t worst_jump_at = 0;
static bool below_min_seen = false;
static void run_until(uint32_t t) {
  while (sim_ms < t) {
    float before = duty();
    loop();
    float after = duty(), step = after - before;
    if (before == 0 && after <= MIN_RUN_PCT + 0.2f) step = 0;      // the start kick
    if (step > worst_jump) { worst_jump = step; worst_jump_at = sim_ms; }
    if (after > 0 && after < MIN_RUN_PCT - 0.2f) below_min_seen = true;
  }
}
static void reset_sim(float vbat) {
  sim_ms = 0; sim_vbat = vbat; sim_serial_in.clear(); sim_serial_out.clear();
  for (auto &d : sim_duty) d = 0;
  for (auto &a : sim_attached) a = 0;
  currentPct = targetPct = startPct = 0; rampStart = stepStart = 0; rampMs = 1000;
  stepIdx = 0; programRunning = true; faulted = false; manualRampMs = 1000;
  worst_jump = 0; below_min_seen = false;
  setup();
}
[[maybe_unused]] static void send(const char *line) { sim_serial_in += line; sim_serial_in += "\n"; }

#ifdef POT_TEST
// built from a copy of the sketch with USE_POT = true
int main() {
  std::printf("speed pot (USE_POT = true)\n");
  sim_pot_frac = 0.0f; reset_sim(12.6f);
  run_until(sim_ms + 1000);
  CHECK(duty() == 0 && !programRunning, "pot at zero: motor off, program off (duty %.1f)", duty());
  sim_pot_frac = 0.75f; run_until(sim_ms + 100);
  CHECK(duty() < 75, "pot turned fast: output ramps, not a step (%.1f)", duty());
  run_until(sim_ms + 400); CHECK(std::fabs(duty() - 75) < 1, "follows pot to 75 %%: %.1f", duty());
  sim_pot_frac = 0.01f; run_until(sim_ms + 400); CHECK(duty() == 0, "bottom of travel is off: %.1f", duty());
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
#else
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
