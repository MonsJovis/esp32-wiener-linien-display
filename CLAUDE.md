# CLAUDE.md

## Project Overview

ESP32-S3 based real-time public transport departure display for Vienna (Wiener Linien). The device fetches live departure data from the Wiener Linien OGD API and displays upcoming departures on a 4.2" e-paper screen. Features external configuration, automatic Wi-Fi reconnection, and signed over-the-air app updates.

## Architecture

```
main.py                 # Entry point, initialization, main loop
boot.py                 # Installs staged OTA updates, rolls back failed ones
config.json             # The device's own settings (stops, lines, names); never in an update
secrets.json            # Wi-Fi credentials (not in git)
lib/
  config.py             # Configuration loader: config.json over DEFAULTS (lazy-cached)
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

Two layers. `config.json` belongs to the device: only `deploy.sh` (USB) writes it, an OTA
update never does (`lib/ota_policy.path_allowed`). It holds what is the device's own:

```json
{
  "stops": [
    {"diva": "60201438", "lines": {"49": [], "46": [], "N49": ["R"], "47A": []}},
    {"diva": "60200956", "lines": {"U4": ["H"]}},
    {"diva": "60200113", "lines": {"52": ["R"]}}
  ],
  "line_priority": ["49", "46", "N49", "U4", "47A", "52"],
  "destination_shortnames": {"HEILIGENSTADT": "Heiligenst.", "...": "..."}
}
```

Everything else has a default in `lib/config.py` `DEFAULTS`, which ships with the app:
`update_interval_sec` 45 (lower runs into the API rate limit), `animation_interval_sec` 1,
`full_refresh_interval_cycles` 600, `wlan` {60, 5, 10}, `stale_restart_threshold_sec` 300,
`watchdog_timeout_ms` 90000, `ota` {`manifest_url` this repo's latest release, `install_hours`
[3, 5]}. A key in `config.json` overrides its default (`wlan`/`ota` key by key); `"manifest_url": ""`
turns updates off.

- A new setting goes into `DEFAULTS`, never only into `config.json`: devices keep their old one.
- Keep defaults out of the repo's `config.json`: a key there pins the value on the device, and
  later releases can no longer change it.
- `stops[].lines`: Empty array = all directions, `["R"]` = outbound, `["H"]` = inbound
- Wi-Fi credentials are in `secrets.json` (gitignored), also device-only: USB deploy writes it,
  an update never does.

## E-Paper Display

- **Partial refresh**: Used for regular updates (minimal flashing, ~0.5s)
- **Full refresh**: Every N updates (configurable) to clear ghosting (~3s with flash)
- **Fonts**: Custom bitmap fonts for crisp rendering
  - 24px: Line names (U4, 49, N49, etc.)
  - 16px: Departure times (5', 12', etc.)
  - 8px: Built-in font for destinations and status
- **Rows**: 34/28 px per line group, compact 28/22 px when those would run into the bottom
  row (49 and 46 both ways need it); rows that still do not fit are dropped from the bottom
- **Status indicators** (bottom row, redrawn on a new minute or a changed Wi-Fi/stale state):
  - Left: Current time (HH:MM)
  - Center: Stale data warning (triangle icon + "STALE Xs") when data is stale
  - Right: Wi-Fi signal bars (connected) or X (disconnected)

## Development

**Deployment**: Use `mpremote` to upload files to ESP32-S3:

```bash
./deploy.sh                       # Deploys all files; finds the one USB serial port itself
./deploy.sh /dev/cu.usbserial-110 # Port name changes with the USB socket (-10, -110, -1140)
```

A deploy stamps `git describe` into `lib/version.py` (`0.0.0-<hash>` before the first tag) and
deletes `ota/state.json`, so a USB deploy always wins over an OTA install in progress.

**Firmware**: MicroPython 1.27.0, build `ESP32_GENERIC_S3-SPIRAM_OCT` (`esptool write_flash -z 0`,
no `erase_flash`, keeps the files). The board's ESP32-S3 has 8 MB of embedded octal PSRAM; the
default S3 build only probes quad PSRAM, logs `PSRAM chip is not connected, or wrong PSRAM line
mode` at boot and runs on internal RAM only (about 100-120k free before a request). The ENOMEM
rules under Conventions come from that setup.

**Credentials**: Create `secrets.json` in project root (not in git):

```json
{
  "wifi": {
    "ssid": "YOUR_SSID",
    "password": "YOUR_PASSWORD"
  }
}
```

**Modifying monitored lines**: Edit `config.json` and `./deploy.sh` (USB) - no code changes
needed, but no release reaches the device's config either.

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
  `"ota": {"install_hours": [0, 24]}` added to the device and reset. Watch the serial log for
  `ota: confirmed X.Y.Z` (v1.0.0 passed this way), then `./deploy.sh` again: an update no
  longer touches `config.json`, so the override stays until a USB deploy removes it.
- `Updater.poll()` runs in the fetch branch right after `clear_cached_departures()` (TLS
  needs that memory). It checks daily, installs only in `ota.install_hours`, then resets.
- `boot.py` moves `ota/new/` into place, counts trial boots, rolls back after 3 without
  `Updater.fetch_ok()` reaching 3. Resets for want of network go through
  `lib/ota.mark_offline()` / `offline_reset()` (stale restart, failed Wi-Fi at boot) and count
  separately, up to 24. It is not part of the payload; changing it, or the `ota/state.json`
  format it shares with `lib/ota.py`, needs a USB deploy.
- Own HTTPS client in `lib/ota.py`: refuses redirects to anything but https and streams the
  bundle with the watchdog fed per 1 KB. (MicroPython 1.24's `requests` kept the old Host
  header across GitHub's redirects; 1.27's follows them fine.)

## Key Modules

- **config.py**: Lazy-loads config.json over `DEFAULTS`, caches it, provides getter functions
- **crowpanel.py**: Hardware abstraction for CrowPanel board (buttons, LED, display init)
- **wifi_manager.py**: WLANManager class with `connect()`, `reconnect()`, `is_connected()`
- **display.py**: All rendering functions, Wi-Fi status indicator, animation state

## Conventions

- MicroPython imports: `ujson`, `utime`, `machine`, `network`
- Memory-constrained: use `gc.collect()` before HTTP requests (3x for TLS)
- Error handling: catch exceptions, display error message, continue polling with stale data
- E-paper optimization: minimize full refreshes, use partial refresh for animations
- Sleep with `utime.sleep()`, not `machine.lightsleep()` (lightsleep trips the watchdog)
- Configuration: every user-configurable value has a default in `lib/config.py` `DEFAULTS` and
  can be overridden in config.json; nothing configurable is hardcoded elsewhere
