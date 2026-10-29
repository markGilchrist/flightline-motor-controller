#!/bin/sh
# Compile motor_pwm.ino on the host against a mock of the Arduino-ESP32 3.x API and run the
# simulation tests, once as shipped and once with USE_POT = true. This checks the C++ and the
# control logic; it does not replace a real ESP32-S3 build (Arduino IDE / arduino-cli) or a bench test.
set -e
D=$(cd "$(dirname "$0")" && pwd)
B="$D/build"; mkdir -p "$B"
CXX="g++ -std=gnu++17 -Wall -Wextra -Werror -O1 -I $D/mock -x c++"
$CXX "$D/test_motor_pwm.cpp" -o "$B/test_motor_pwm"
"$B/test_motor_pwm"
sed 's/^const bool USE_POT  = false;/const bool USE_POT  = true; /' "$D/../motor_pwm/motor_pwm.ino" > "$B/motor_pwm_pot.ino"
grep -q '^const bool USE_POT  = true;' "$B/motor_pwm_pot.ino"
$CXX -DPOT_TEST -DSKETCH="\"$B/motor_pwm_pot.ino\"" "$D/test_motor_pwm.cpp" -o "$B/test_motor_pwm_pot"
"$B/test_motor_pwm_pot"
