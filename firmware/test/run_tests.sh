#!/bin/sh
# Compile motor_pwm.ino on the host against a mock of the Arduino-ESP32 3.x API and run the
# simulation tests in four builds: as shipped (parking), PARK_INVERT = true, USE_PARK = false
# (plain program/battery/serial behaviour) and USE_POT = true. This checks the C++ and the control
# logic; it does not replace a real ESP32-S3 build (Arduino IDE / arduino-cli) or a bench test.
set -e
D=$(cd "$(dirname "$0")" && pwd)
B="$D/build"; mkdir -p "$B"
SK="$D/../motor_pwm/motor_pwm.ino"
CXX="g++ -std=gnu++17 -Wall -Wextra -Werror -O1 -I $D/mock -x c++"

variant() {   # variant <name> <sed expression> <expected line after the edit>
  sed "$2" "$SK" > "$B/motor_pwm_$1.ino"
  grep -q "$3" "$B/motor_pwm_$1.ino" || { echo "could not make the $1 variant"; exit 1; }
}
variant nopark 's/^const bool  USE_PARK      = true; /const bool  USE_PARK      = false;/' '^const bool  USE_PARK      = false;'
variant invert 's/^const bool  PARK_INVERT   = false;/const bool  PARK_INVERT   = true; /' '^const bool  PARK_INVERT   = true;'
variant pot    's/^const bool USE_POT  = false;/const bool USE_POT  = true; /' '^const bool USE_POT  = true;'

$CXX -DPARK_TEST "$D/test_motor_pwm.cpp" -o "$B/test_park" && "$B/test_park"
$CXX -DPARK_TEST -DINVERT_TEST -DSKETCH="\"$B/motor_pwm_invert.ino\"" "$D/test_motor_pwm.cpp" -o "$B/test_invert" && "$B/test_invert"
$CXX -DSKETCH="\"$B/motor_pwm_nopark.ino\"" "$D/test_motor_pwm.cpp" -o "$B/test_nopark" && "$B/test_nopark"
$CXX -DPOT_TEST -DSKETCH="\"$B/motor_pwm_pot.ino\"" "$D/test_motor_pwm.cpp" -o "$B/test_pot" && "$B/test_pot"
