# CLAUDE.md

## Project Overview

ESP32-based real-time public transport departure display for Vienna (Wiener Linien). The device fetches live departure data from an API and displays upcoming departures on a 160x128 LCD screen, refreshing every 30 seconds.

## Architecture

```
main.py                 # Entry point, initialization, main loop
boot.py                 # MicroPython boot (empty)
lib/
  display.py            # LCD rendering (line names, departure times)
  get_data.py           # API fetching with URL-encoded filters
  init_wifi.py          # Wi-Fi connection with retry logic
  led.py                # Status LED control (GPIO pin 2)
  parse_datetime.py     # ISO 8601 timestamp parsing
  secrets.py            # Loads Wi-Fi credentials from secrets.json
  urlencode.py          # URL encoding (supports German umlauts)
  utils.py              # Helper functions (zero-padding)
  st7735/               # Display driver library (external)
```

## Hardware

- **MCU**: ESP32
- **Display**: ST7735 160x128 LCD via SPI (pins: SCK=14, MOSI=13, MISO=12, clock=20MHz)
- **LED**: GPIO pin 2 for status indication

## Code Flow

1. `main()` → `initialize()`: LED on, display init, Wi-Fi connect
2. `start_main_loop()`: 30-second polling loop
   - Fetch data from `https://wl-proxy.monsjovis.dev/monitor/next-departures`
   - Parse and sort departures by priority (U4, 49, N49, 46, N46, 47A, 52 first)
   - Render to display with countdown times
   - 60-second watchdog timer prevents hangs

## Development

**Deployment**: Use Pymakr VS Code extension to upload files to ESP32.

**Credentials**: Create `secrets.json` in project root (not in git):
```json
{
  "wifi_ssid": "YOUR_SSID",
  "wifi_password": "YOUR_PASSWORD"
}
```

**Modifying monitored lines**: Edit the `filter` list in `lib/get_data.py`. Each entry has:
- `diva`: Stop ID
- `lines`: Array of `{name, direction}` (R=outbound, H=inbound)

## Conventions

- MicroPython imports: `ujson`, `utime`, `machine`, `network`
- Memory-constrained: use `gc.collect()` when needed
- Error handling: catch exceptions, display error message, blink LED, continue polling
