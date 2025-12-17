#!/bin/bash
PORT=${1:-/dev/cu.usbserial-140}

echo "Deploying to $PORT..."

mpremote connect $PORT fs mkdir lib 2>/dev/null

mpremote connect $PORT fs cp main.py boot.py secrets.json config.json :
mpremote connect $PORT fs cp lib/*.py :lib/

echo "Done. Resetting device..."
mpremote connect $PORT reset
