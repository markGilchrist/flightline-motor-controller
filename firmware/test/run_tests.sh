#!/bin/sh
# Compile motor_pwm.ino on the host against mocks of the Arduino-ESP32 3.x API (incl. BLE and
# Preferences) and run the simulation tests in six builds:
#   app     as shipped: the FlightLine app protocol over Bluetooth, the test plays the phone
#   magnet  FL_DEVICE_TYPE = 2 (the app's magnet card)
#   park    step program from power-up: wiper parking with four park-switch types
#   invert  as park, with PARK_INVERT = true
#   nopark  step program, USE_PARK = false: program, battery and serial behaviour
#   pot     USE_POT = true
# This checks the C++ and the control logic; it does not replace a real ESP32-S3 build
# (Arduino IDE / arduino-cli) or a bench test with the app.
set -e
D=$(cd "$(dirname "$0")" && pwd)
B="$D/build"; mkdir -p "$B"
SK="$D/../motor_pwm/motor_pwm.ino"
CXX="g++ -std=gnu++17 -Wall -Wextra -Werror -O1 -I $D/mock -x c++"

PROG='s/^const Mode START_MODE = MODE_APP;/const Mode START_MODE = MODE_PROGRAM;/'
NOPARK='s/^const bool  USE_PARK      = true; /const bool  USE_PARK      = false;/'
INVERT='s/^const bool  PARK_INVERT   = false;/const bool  PARK_INVERT   = true; /'
MAGNET='s/^const uint8_t  FL_DEVICE_TYPE = 1;/const uint8_t  FL_DEVICE_TYPE = 2;/'
POT='s/^const bool USE_POT  = false;/const bool USE_POT  = true; /'

variant() {   # variant <name> <expected line after the edit> <sed expression>...
  name=$1; check=$2; shift 2
  cp "$SK" "$B/motor_pwm_$name.ino"
  for e in "$@"; do sed -i "$e" "$B/motor_pwm_$name.ino"; done
  grep -q "$check" "$B/motor_pwm_$name.ino" || { echo "could not make the $name variant"; exit 1; }
}
variant magnet '^const uint8_t  FL_DEVICE_TYPE = 2;' "$MAGNET"
variant park   '^const Mode START_MODE = MODE_PROGRAM;' "$PROG"
variant invert '^const bool  PARK_INVERT   = true;' "$PROG" "$INVERT"
variant nopark '^const bool  USE_PARK      = false;' "$PROG" "$NOPARK"
variant pot    '^const bool USE_POT  = true;' "$POT"

run() {   # run <name> <defines...>
  name=$1; shift
  $CXX "$@" "$D/test_motor_pwm.cpp" -o "$B/test_$name" && "$B/test_$name"
}
run app    -DAPP_TEST
run magnet -DMAGNET_TEST -DSKETCH="\"$B/motor_pwm_magnet.ino\""
run park   -DPARK_TEST -DSKETCH="\"$B/motor_pwm_park.ino\""
run invert -DPARK_TEST -DINVERT_TEST -DSKETCH="\"$B/motor_pwm_invert.ino\""
run nopark -DSKETCH="\"$B/motor_pwm_nopark.ino\""
run pot    -DPOT_TEST -DSKETCH="\"$B/motor_pwm_pot.ino\""
