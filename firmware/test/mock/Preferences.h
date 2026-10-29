// Host-side stand-in for Preferences (NVS). The store outlives a simulated reboot, like flash does.
#pragma once
#include <map>
#include <string>
#include <cstdint>
extern std::map<std::string, uint8_t> sim_flash;
extern int sim_flash_writes;
class Preferences {
 public:
  bool begin(const char *ns, bool = false, const char * = nullptr) { ns_ = ns; return true; }
  uint8_t getUChar(const char *k, uint8_t def = 0) { auto it = sim_flash.find(ns_ + "/" + k); return it == sim_flash.end() ? def : it->second; }
  size_t putUChar(const char *k, uint8_t v) { sim_flash[ns_ + "/" + k] = v; sim_flash_writes++; return 1; }
 private:
  std::string ns_;
};
