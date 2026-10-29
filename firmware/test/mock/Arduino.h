// Minimal host-side stand-in for the Arduino-ESP32 3.x API used by motor_pwm.ino.
// Signatures follow cores/esp32 in arduino-esp32 3.3.x (esp32-hal-ledc.h, esp32-hal-adc.h, Arduino.h).
// Time is simulated: millis() returns sim_ms, delay() advances it.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstdlib>
#include <cmath>
#include <string>
#include <deque>
#include <algorithm>

using std::min;
using std::max;
#define constrain(amt, low, high) ((amt) < (low) ? (low) : ((amt) > (high) ? (high) : (amt)))
#define LOW 0
#define HIGH 1
#define OUTPUT 0x03

typedef enum { ADC_0db, ADC_2_5db, ADC_6db, ADC_11db, ADC_ATTENDB_MAX } adc_attenuation_t;

// ---- simulation state (defined in the test) ----
extern uint32_t sim_ms;
extern float sim_vbat;          // battery voltage at J1
extern float sim_pot_frac;      // pot wiper 0..1
extern uint32_t sim_duty[64];   // last ledcWrite per pin
extern int sim_attached[64];    // resolution in bits, 0 = not attached
extern int sim_level[64];       // last digitalWrite per pin
extern std::string sim_serial_in, sim_serial_out;

inline uint32_t millis() { return sim_ms; }
inline void delay(uint32_t ms) { sim_ms += ms; }
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t pin, uint8_t val) { sim_level[pin] = val; }
inline bool ledcAttach(uint8_t pin, uint32_t freq, uint8_t resolution) {
  sim_attached[pin] = resolution; (void)freq; return true;
}
inline bool ledcWrite(uint8_t pin, uint32_t duty) {
  if (!sim_attached[pin]) { std::fprintf(stderr, "ledcWrite on unattached pin %u\n", pin); std::abort(); }
  sim_duty[pin] = duty; return true;
}
inline void analogSetPinAttenuation(uint8_t, adc_attenuation_t) {}
// GPIO1 sees VBAT through 100k/18k; 11 dB range tops out near 3.1 V
inline uint32_t analogReadMilliVolts(uint8_t pin) {
  if (pin != 1) return 0;
  float mv = sim_vbat * 18.0f / 118.0f * 1000.0f;
  return (uint32_t)std::lround(std::min(std::max(mv, 0.0f), 3100.0f));
}
inline uint16_t analogRead(uint8_t) { return (uint16_t)std::lround(sim_pot_frac * 4095.0f); }

class String {
 public:
  String() {}
  String(const char *s) : s_(s) {}
  String(const std::string &s) : s_(s) {}
  String &operator+=(char c) { s_ += c; return *this; }
  String &operator=(const char *s) { s_ = s; return *this; }
  bool operator==(const char *o) const { return s_ == o; }
  unsigned int length() const { return s_.size(); }
  void trim() {
    size_t a = s_.find_first_not_of(" \t\r\n"), b = s_.find_last_not_of(" \t\r\n");
    s_ = (a == std::string::npos) ? "" : s_.substr(a, b - a + 1);
  }
  bool startsWith(const char *p) const { return s_.rfind(p, 0) == 0; }
  String substring(unsigned int from) const { return from >= s_.size() ? String() : String(s_.substr(from)); }
  float toFloat() const { return std::strtof(s_.c_str(), nullptr); }
  long toInt() const { return std::strtol(s_.c_str(), nullptr, 10); }
 private:
  std::string s_;
};

struct SerialMock {
  void begin(unsigned long) {}
  int available() { return (int)sim_serial_in.size(); }
  int read() { if (sim_serial_in.empty()) return -1; char c = sim_serial_in[0]; sim_serial_in.erase(0, 1); return c; }
  size_t println(const char *s) { sim_serial_out += s; sim_serial_out += "\n"; return 0; }
  size_t printf(const char *fmt, ...) __attribute__((format(printf, 2, 3))) {
    char buf[256]; va_list ap; va_start(ap, fmt); int n = std::vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
    sim_serial_out += buf; return n;
  }
};
extern SerialMock Serial;
