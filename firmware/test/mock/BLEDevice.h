// Host-side stand-in for the Arduino-ESP32 3.x BLE library (Bluedroid flavour), just enough for
// motor_pwm.ino. It records what the sketch sets up and lets tests play the phone:
// sim_ble_connect(), sim_ble_write("aS128"), and the notifications in sim_ble_notified.
#pragma once
#include "Arduino.h"
#include <vector>
#include <string>

class BLEUUID {
 public:
  BLEUUID() {}
  BLEUUID(uint16_t u) : v(u) {}
  uint16_t v = 0;
};

class BLEDescriptor { public: virtual ~BLEDescriptor() {} uint16_t uuid = 0; };
class BLE2902 : public BLEDescriptor { public: BLE2902() { uuid = 0x2902; } };

class BLECharacteristic;
class BLECharacteristicCallbacks {
 public:
  virtual ~BLECharacteristicCallbacks() {}
  virtual void onWrite(BLECharacteristic *) {}
};

extern std::vector<std::string> sim_ble_notified;

class BLECharacteristic {
 public:
  static const uint32_t PROPERTY_READ = 1 << 0, PROPERTY_WRITE = 1 << 1, PROPERTY_NOTIFY = 1 << 2,
                        PROPERTY_BROADCAST = 1 << 3, PROPERTY_INDICATE = 1 << 4, PROPERTY_WRITE_NR = 1 << 5;
  BLECharacteristic(BLEUUID u, uint32_t p) : uuid(u), props(p) {}
  void addDescriptor(BLEDescriptor *d) { descriptors.push_back(d); }
  void setCallbacks(BLECharacteristicCallbacks *c) { callbacks = c; }
  void setValue(const uint8_t *data, size_t size) { value.assign((const char *)data, size); }
  String getValue() const { return String(value); }
  void notify(bool = true) { sim_ble_notified.push_back(value); }
  BLEUUID uuid; uint32_t props;
  std::vector<BLEDescriptor *> descriptors;
  BLECharacteristicCallbacks *callbacks = nullptr;
  std::string value;
};

class BLEService {
 public:
  explicit BLEService(BLEUUID u) : uuid(u) {}
  BLECharacteristic *createCharacteristic(BLEUUID u, uint32_t props) {
    chars.push_back(new BLECharacteristic(u, props)); return chars.back();
  }
  void start() { started = true; }
  BLEUUID uuid; bool started = false;
  std::vector<BLECharacteristic *> chars;
};

class BLEServer;
class BLEServerCallbacks {
 public:
  virtual ~BLEServerCallbacks() {}
  virtual void onConnect(BLEServer *) {}
  virtual void onDisconnect(BLEServer *) {}
};

class BLEServer {
 public:
  BLEService *createService(BLEUUID u, uint32_t = 15, uint8_t = 0) { services.push_back(new BLEService(u)); return services.back(); }
  void setCallbacks(BLEServerCallbacks *c) { callbacks = c; }
  std::vector<BLEService *> services;
  BLEServerCallbacks *callbacks = nullptr;
};

class BLEAdvertising {
 public:
  void addServiceUUID(BLEUUID u) { uuids.push_back(u.v); }
  void setScanResponse(bool b) { scanResponse = b; }
  std::vector<uint16_t> uuids; bool scanResponse = false;
};

struct SimBle {
  std::string name; BLEServer *server = nullptr; BLEAdvertising adv; int advertisingStarts = 0;
};
extern SimBle sim_ble;

class BLEDevice {
 public:
  static void init(String name) { sim_ble = SimBle(); sim_ble.name = name.c_str(); }
  static BLEServer *createServer() { sim_ble.server = new BLEServer(); return sim_ble.server; }
  static BLEAdvertising *getAdvertising() { return &sim_ble.adv; }
  static void startAdvertising() { sim_ble.advertisingStarts++; }
};

// ---- test helpers: act as the phone ----
inline BLECharacteristic *sim_ble_find(uint16_t svc, uint16_t chr) {
  if (!sim_ble.server) return nullptr;
  for (auto *s : sim_ble.server->services)
    if (s->uuid.v == svc) for (auto *c : s->chars) if (c->uuid.v == chr) return c;
  return nullptr;
}
inline void sim_ble_connect() { sim_ble.server->callbacks->onConnect(sim_ble.server); }
inline void sim_ble_disconnect() { sim_ble.server->callbacks->onDisconnect(sim_ble.server); }
inline void sim_ble_write(const std::string &bytes) {      // write without response to FFE1
  BLECharacteristic *c = sim_ble_find(0xFFE0, 0xFFE1);
  c->value = bytes; c->callbacks->onWrite(c);
}
