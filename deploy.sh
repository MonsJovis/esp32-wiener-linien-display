#!/bin/bash
PORT=${1:-/dev/cu.usbserial-140}

echo "Deploying to $PORT..."

mpremote connect $PORT fs mkdir lib 2>/dev/null
mpremote connect $PORT fs mkdir lib/st7735 2>/dev/null

mpremote connect $PORT fs cp main.py boot.py secrets.json :
mpremote connect $PORT fs cp lib/*.py :lib/
mpremote connect $PORT fs cp lib/st7735/*.py :lib/st7735/

echo "Done. Resetting device..."
mpremote connect $PORT reset
