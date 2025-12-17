# CLAUDE.md

## Project Overview

ESP32-S3 based real-time public transport departure display for Vienna (Wiener Linien). The device fetches live departure data from the Wiener Linien OGD API and displays upcoming departures on a 4.2" e-paper screen. Features external configuration, automatic Wi-Fi reconnection, and power-efficient light sleep.

## Architecture

```
main.py                 # Entry point, initialization, main loop
boot.py                 # MicroPython boot (empty)
config.json             # External configuration (stops, lines, intervals)
secrets.json            # Wi-Fi credentials (not in git)
lib/
  config.py             # Configuration loader (lazy-cached)
  crowpanel.py          # Hardware abstraction (buttons, LED, display)
  wifi_manager.py       # Wi-Fi connection class with reconnect support
  display.py            # E-paper rendering (line names, departure times)
  fonts.py              # Bitmap fonts (24px for line names, 16px for times)
  ssd1683.py            # SSD1683 e-paper display driver
  get_data.py           # API fetching and response transformation
  init_wifi.py          # Timezone handling and NTP sync
  secrets.py            # Loads Wi-Fi credentials from secrets.json
  urlencode.py          # URL encoding (supports German umlauts)
  utils.py              # Helper functions (zero-padding)
```

## Hardware

- **MCU**: ESP32-S3 (CrowPanel 4.2" E-Paper HMI)
- **Display**: SSD1683 400x300 e-paper via SPI
- **Buttons**: HOME=2, EXIT=1, Rotary: PREV=6, DONE=5, NEXT=4
- **LED**: Power LED on pin 41

## Code Flow

1. `main()` → `initialize()`:
   - Initialize watchdog timer (configurable timeout)
   - Initialize CrowPanel hardware abstraction
   - Initialize display, show boot screen
   - Create WLANManager, connect to Wi-Fi
   - Sync time via NTP

2. `start_main_loop()`: Configurable polling loop (default 30s)
   - Check button presses (HOME = force refresh)
   - Check Wi-Fi connection, reconnect if needed
   - Fetch data from Wiener Linien OGD API
   - Filter by configured lines/directions
   - Sort by priority (configurable in config.json)
   - Render to display with countdown times
   - Draw Wi-Fi status indicator
   - Light sleep for power efficiency

## Configuration

All settings are in `config.json`:

```json
{
  "stops": [
    {"diva": "60201438", "lines": {"49": [], "N49": ["R"], "47A": []}},
    {"diva": "60200956", "lines": {"U4": ["H"]}}
  ],
  "line_priority": ["49", "N49", "U4", "47A", "52"],
  "update_interval": 30,
  "animation_interval": 4,
  "full_refresh_interval": 40,
  "wlan": {"timeout": 60, "reconnect_delay": 5},
  "watchdog_timeout": 90000
}
```

- `stops[].lines`: Empty array = all directions, `["R"]` = outbound, `["H"]` = inbound
- Wi-Fi credentials remain in `secrets.json` (gitignored)

## E-Paper Display

- **Partial refresh**: Used for regular updates (minimal flashing, ~0.5s)
- **Full refresh**: Every N updates (configurable) to clear ghosting (~3s with flash)
- **Fonts**: Custom bitmap fonts for crisp rendering
  - 24px: Line names (U4, 49, N49, etc.)
  - 16px: Departure times (5', 12', etc.)
  - 8px: Built-in font for destinations and status
- **Status indicators**: Wi-Fi signal bars, stale data asterisk (top-right)

## Development

**Deployment**: Use `mpremote` to upload files to ESP32-S3:

```bash
./deploy.sh              # Deploys all files including config.json
./deploy.sh /dev/ttyUSB0 # Specify custom port
```

**Firmware**: Flash MicroPython for ESP32-S3 (with SPIRAM support recommended).

**Credentials**: Create `secrets.json` in project root (not in git):

```json
{
  "wifi_ssid": "YOUR_SSID",
  "wifi_password": "YOUR_PASSWORD"
}
```

**Modifying monitored lines**: Edit `config.json` - no code changes needed.

## Key Modules

- **config.py**: Lazy-loads and caches config.json, provides getter functions
- **crowpanel.py**: Hardware abstraction for CrowPanel board (buttons, LED, display init)
- **wifi_manager.py**: WLANManager class with `connect()`, `reconnect()`, `is_connected()`
- **display.py**: All rendering functions, Wi-Fi status indicator, animation state

## Conventions

- MicroPython imports: `ujson`, `utime`, `machine`, `network`
- Memory-constrained: use `gc.collect()` before HTTP requests (3x for TLS)
- Error handling: catch exceptions, display error message, continue polling with stale data
- E-paper optimization: minimize full refreshes, use partial refresh for animations
- Power efficiency: use `machine.lightsleep()` between updates
- Configuration: all user-configurable values in config.json, not hardcoded
