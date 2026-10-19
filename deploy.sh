#!/bin/bash
PORT=${1:-/dev/cu.usbserial-1140}

# The device compares this with each release: a deploy made at or after the
# v1.2.0 tag ("1.2.0-3-gabc") is replaced by v1.2.1, not by v1.2.0 again.
VERSION=$(git describe --tags --dirty 2>/dev/null || echo "0.0.0-$(git rev-parse --short HEAD)")
VERSION_FILE=$(mktemp)
echo "VERSION = '${VERSION#v}'" > "$VERSION_FILE"

echo "Deploying ${VERSION#v} to $PORT..."

mpremote connect $PORT fs mkdir lib 2>/dev/null

mpremote connect $PORT fs cp main.py boot.py secrets.json config.json :
mpremote connect $PORT fs cp lib/*.py :lib/
mpremote connect $PORT fs cp "$VERSION_FILE" :lib/version.py
rm "$VERSION_FILE"

# A USB deploy overrides any OTA install in progress. Without this, boot.py
# could roll the deployed files back to an older OTA backup.
mpremote connect $PORT fs rm :ota/state.json 2>/dev/null

echo "Done. Resetting device..."
mpremote connect $PORT reset
