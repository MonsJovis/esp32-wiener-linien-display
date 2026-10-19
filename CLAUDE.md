# CLAUDE.md

## Project Overview

ESP32-S3 based real-time public transport departure display for Vienna (Wiener Linien). The device fetches live departure data from the Wiener Linien OGD API and displays upcoming departures on a 4.2" e-paper screen. Features external configuration, automatic Wi-Fi reconnection, and signed over-the-air app updates.

## Architecture

```
main.py                 # Entry point, initialization, main loop
boot.py                 # Installs staged OTA updates, rolls back failed ones
config.json             # External configuration (stops, lines, intervals, ota)
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
  ota.py                # OTA: daily check, download/stage, trial confirm, HTTPS client
  ota_policy.py         # OTA rules, pure Python (also run by tools/ and tests/)
  ota_key.py            # Public half of the release signing key
  version.py            # Running version, stamped by tools/release.py and deploy.sh
tools/release.py        # Builds, verifies an OTA release; writes lib/ota_key.py
tests/                  # Host tests (python3 -m unittest discover tests)
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

2. `start_main_loop()`: 1s tick, fetches every `update_interval_sec` (45s)
   - Check button presses (HOME = force refresh)
   - Check Wi-Fi connection, reconnect if needed
   - OTA: `Updater.poll()` (daily check, night install, see below)
   - Fetch data from Wiener Linien OGD API
   - Filter by configured lines/directions
   - Sort by priority (configurable in config.json)
   - Render to display with countdown times
   - Draw Wi-Fi status indicator
   - `utime.sleep(1)`, not `machine.lightsleep()`: lightsleep trips the watchdog

## Configuration

All settings are in `config.json`:

```json
{
  "stops": [
    {"diva": "60201438", "lines": {"49": [], "46": [], "N49": ["R"], "47A": []}},
    {"diva": "60200956", "lines": {"U4": ["H"]}},
    {"diva": "60200113", "lines": {"52": ["R"]}}
  ],
  "line_priority": ["49", "46", "N49", "U4", "47A", "52"],
  "destination_shortnames": {"HEILIGENSTADT": "Heiligenst.", "...": "..."},
  "update_interval_sec": 45,
  "animation_interval_sec": 1,
  "full_refresh_interval_cycles": 600,
  "wlan": {"timeout_sec": 60, "reconnect_delay_sec": 5, "max_retries": 10},
  "stale_restart_threshold_sec": 300,
  "watchdog_timeout_ms": 90000,
  "ota": {"manifest_url": "https://github.com/MonsJovis/esp32-wiener-linien-display/releases/latest/download/manifest.json",
          "install_hours": [3, 5]}
}
```

- `stops[].lines`: Empty array = all directions, `["R"]` = outbound, `["H"]` = inbound
- `update_interval_sec` 45: lower runs into the API rate limit
- `config.json` ships with every OTA release, so config changes reach the device by tag too
- Wi-Fi credentials remain in `secrets.json` (gitignored)

## E-Paper Display

- **Partial refresh**: Used for regular updates (minimal flashing, ~0.5s)
- **Full refresh**: Every N updates (configurable) to clear ghosting (~3s with flash)
- **Fonts**: Custom bitmap fonts for crisp rendering
  - 24px: Line names (U4, 49, N49, etc.)
  - 16px: Departure times (5', 12', etc.)
  - 8px: Built-in font for destinations and status
- **Status indicators** (bottom row):
  - Left: Current time (HH:MM)
  - Center: Stale data warning (triangle icon + "STALE Xs") when data is stale
  - Right: Wi-Fi signal bars (connected) or X (disconnected)

## Development

**Deployment**: Use `mpremote` to upload files to ESP32-S3:

```bash
./deploy.sh                      # Deploys all files including config.json
./deploy.sh /dev/cu.usbserial-10 # Port changes with the USB socket: ls /dev/cu.usbserial-*
```

A deploy stamps `git describe` into `lib/version.py` (`0.0.0-<hash>` before the first tag) and
deletes `ota/state.json`, so a USB deploy always wins over an OTA install in progress.

**Firmware**: Flash MicroPython for ESP32-S3 (with SPIRAM support recommended). The firmware on
the current board logs `PSRAM chip is not connected, or wrong PSRAM line mode` at boot and runs
on internal RAM only: about 100-120k free before a request.

**Credentials**: Create `secrets.json` in project root (not in git):

```json
{
  "wifi_ssid": "YOUR_SSID",
  "wifi_password": "YOUR_PASSWORD"
}
```

**Modifying monitored lines**: Edit `config.json` - no code changes needed.

**Linting**: This project uses [ruff](https://docs.astral.sh/ruff/) for code quality:

```bash
pip install -r requirements-dev.txt
ruff check .
```

Lint and the host tests (`python3 -m unittest discover tests`) run on push/PR to main via
GitHub Actions.

## OTA updates

- Release = tag `vX.Y.Z` (`git tag -a v1.0.1 -m "..." && git push origin v1.0.1`) →
  `.github/workflows/release.yml` publishes `app-X.Y.Z.bin`, `manifest.json`, `manifest.sig`
  (signing key: Actions secret `OTA_SIGNING_KEY`; backup in 1Password, private account, vault
  Schaurich). The device checks 5 min after boot, then daily.
- Testing an install by day: USB-deploy before tagging, then copy a `config.json` with
  `"install_hours": [0, 24]` to the device and reset. The release's own `config.json` puts the
  window back to 3-5. Watch the serial log for `ota: confirmed X.Y.Z` (v1.0.0 passed this way).
- `Updater.poll()` runs in the fetch branch right after `clear_cached_departures()` (TLS
  needs that memory). It checks daily, installs only in `ota.install_hours`, then resets.
- `boot.py` moves `ota/new/` into place, counts trial boots, rolls back after 3 without
  `Updater.fetch_ok()` reaching 3. It is not part of the payload; changing it, or the
  `ota/state.json` format it shares with `lib/ota.py`, needs a USB deploy.
- Own HTTPS client in `lib/ota.py`: `requests` in MicroPython 1.24 keeps the old Host header
  across redirects, and GitHub redirects every release download to another host.

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
- Sleep with `utime.sleep()`, not `machine.lightsleep()` (lightsleep trips the watchdog)
- Configuration: all user-configurable values in config.json, not hardcoded
