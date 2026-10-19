#!/bin/bash
cd "$(dirname "$0")" || exit 1  # the paths below and git describe are the repo's
# The port name moves with the USB socket (cu.usbserial-10, -110, -1140), so
# without an argument take the one USB serial port there is.
PORT=$1
if [ -z "$PORT" ]; then
    PORTS=(/dev/cu.usbserial-* /dev/cu.usbmodem*)
    PORTS=($(ls "${PORTS[@]}" 2>/dev/null))
    if [ ${#PORTS[@]} -ne 1 ]; then
        echo "Found ${#PORTS[@]} USB serial ports (${PORTS[*]}). Pass one: ./deploy.sh /dev/cu.usbserial-..." >&2
        exit 1
    fi
    PORT=${PORTS[0]}
fi

# The device compares this with each release: a deploy made at or after the
# v1.2.0 tag ("1.2.0-3-gabc") is replaced by v1.2.1, not by v1.2.0 again.
VERSION=$(git describe --tags --dirty 2>/dev/null || echo "0.0.0-$(git rev-parse --short HEAD)")
VERSION_FILE=$(mktemp)
echo "VERSION = '${VERSION#v}'" > "$VERSION_FILE"

echo "Deploying ${VERSION#v} to $PORT..."

# One mpremote session, and first the watchdog: main.py feeds it until mpremote
# interrupts it, and 90 s later it resets the board in the middle of a copy.
# WDT() on the ESP32 reconfigures the running one, so this gives the copy 5 min.
# Removing ota/state.json: a USB deploy overrides any OTA install in progress.
# Without this, boot.py could roll the deployed files back to an older OTA backup.
mpremote connect "$PORT" \
    exec "from machine import WDT
WDT(timeout=300000)
import os
try:
    os.mkdir('lib')
except OSError:
    pass" \
    + fs cp main.py boot.py secrets.json config.json : \
    + fs cp lib/*.py :lib/ \
    + fs cp "$VERSION_FILE" :lib/version.py \
    + exec "import os
try:
    os.remove('ota/state.json')
except OSError:
    pass" \
    + reset
STATUS=$?
rm "$VERSION_FILE"
[ $STATUS -eq 0 ] && echo "Done. The device restarts." || echo "Deploy FAILED ($STATUS)" >&2
exit $STATUS
