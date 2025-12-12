# CLAUDE.md

## Project Overview

ESP32-S3 based real-time public transport departure display for Vienna (Wiener Linien). The device fetches live departure data from an API and displays upcoming departures on a 4.2" e-paper screen, refreshing every 30 seconds.

## Architecture

```
main.py                 # Entry point, initialization, main loop
boot.py                 # MicroPython boot (empty)
lib/
  display.py            # E-paper rendering (line names, departure times)
  fonts.py              # Bitmap fonts (24px for line names, 16px for times)
  ssd1683.py            # SSD1683 e-paper display driver
  get_data.py           # API fetching with URL-encoded filters
  init_wifi.py          # Wi-Fi connection with retry logic
  parse_datetime.py     # ISO 8601 timestamp parsing
  secrets.py            # Loads Wi-Fi credentials from secrets.json
  urlencode.py          # URL encoding (supports German umlauts)
  utils.py              # Helper functions (zero-padding)
```

## Hardware

- **MCU**: ESP32-S3 (CrowPanel 4.2" E-Paper HMI)
- **Display**: SSD1683 400x300 e-paper via SPI
- **Buttons**: HOME=2, EXIT=1, Rotary: PREV=4, DONE=5, NEXT=6

## Code Flow

1. `main()` → `initialize()`: LED on, display init, Wi-Fi connect
2. `start_main_loop()`: 30-second polling loop
   - Fetch data from `https://wl-proxy.monsjovis.dev/monitor/next-departures`
   - Parse and sort departures by priority (U4, 49, N49, 46, N46, 47A, 52 first)
   - Render to display with countdown times using bitmap fonts
   - 90-second watchdog timer prevents hangs

## E-Paper Display

- **Partial refresh**: Used for regular updates (minimal flashing, ~0.5s)
- **Full refresh**: Every 10 updates to clear ghosting (~3s with flash)
- **Fonts**: Custom bitmap fonts for crisp rendering
  - 24px: Line names (U4, 49, N49, etc.)
  - 16px: Departure times (5', 12', etc.)
  - 8px: Built-in font for timestamp

## Development

**Deployment**: Use `mpremote` to upload files to ESP32-S3. See also the ./deploy.sh script.

**Firmware**: Flash MicroPython for ESP32-S3 (with SPIRAM support recommended).

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
- E-paper optimization: minimize full refreshes to reduce flashing
