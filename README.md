# ESP32 Wiener Linien Display

Real-time public transport departure display for Vienna (Wiener Linien) running on an ESP32-S3 with a 4.2" e-paper screen.

![MicroPython](https://img.shields.io/badge/MicroPython-1.24-blue)
![ESP32-S3](https://img.shields.io/badge/ESP32--S3-CrowPanel%204.2%22-green)
[![Lint](https://github.com/monsjovis/esp-public-transport-screen/actions/workflows/lint.yml/badge.svg)](https://github.com/monsjovis/esp-public-transport-screen/actions/workflows/lint.yml)

## Features

- Real-time departure data from Wiener Linien API
- Configurable refresh cycle (default: 30 seconds)
- E-paper display with partial refresh (minimal flashing)
- Animated "arriving" indicator for imminent departures
- Grouped display by line with multiple destinations
- External configuration file (no code changes needed)
- Automatic Wi-Fi reconnection for 24/7 operation
- Button support for manual refresh
- Wi-Fi status indicator on display
- Watchdog timer for reliability
- Graceful error handling with stale data fallback

## Hardware

- **MCU**: ESP32-S3 ([CrowPanel 4.2" E-Paper HMI](https://www.elecrow.com/esp32-display-4-2-inch-e-paper-hmi-display-with-400-300-resolution-black-white-display.html))
- **Display**: SSD1683 400x300 e-paper via SPI
- **Power**: USB-C

### Pin Configuration

| Function | Pin |
|----------|-----|
| SPI SCK  | 12  |
| SPI MOSI | 11  |
| CS       | 45  |
| DC       | 46  |
| RST      | 47  |
| BUSY     | 48  |
| PWR      | 7   |
| HOME btn | 2   |
| EXIT btn | 1   |
| LED      | 41  |

## Project Structure

```
├── main.py              # Entry point, main loop
├── boot.py              # MicroPython boot (empty)
├── config.json          # Configuration (stops, lines, intervals)
├── secrets.json         # Wi-Fi credentials (not in git)
├── deploy.sh            # Deployment script
└── lib/
    ├── config.py        # Configuration loader
    ├── crowpanel.py     # Hardware abstraction (buttons, LED)
    ├── wifi_manager.py  # Wi-Fi connection with reconnect
    ├── display.py       # E-paper rendering
    ├── fonts.py         # Bitmap fonts (24px, 16px)
    ├── ssd1683.py       # SSD1683 display driver
    ├── get_data.py      # API fetching and filtering
    ├── init_wifi.py     # Timezone and NTP sync
    ├── secrets.py       # Credential loader
    ├── urlencode.py     # URL encoding
    └── utils.py         # Helper functions
```

## Setup

### 1. Flash MicroPython

Flash [MicroPython for ESP32-S3](https://micropython.org/download/ESP32_GENERIC_S3/) (SPIRAM version recommended for better memory management).

### 2. Configure Wi-Fi

Create `secrets.json` in the project root:

```json
{
  "wifi_ssid": "YOUR_SSID",
  "wifi_password": "YOUR_PASSWORD"
}
```

### 3. Configure Stops and Lines

Edit `config.json` to customize which stops and lines to monitor:

```json
{
  "stops": [
    {
      "diva": "60201438",
      "lines": {
        "49": [],
        "N49": ["R"],
        "47A": []
      }
    },
    {
      "diva": "60200956",
      "lines": {
        "U4": ["H"]
      }
    }
  ],
  "line_priority": ["49", "N49", "U4", "47A", "52"],
  "update_interval": 30,
  "animation_interval": 4,
  "full_refresh_interval": 40,
  "wlan": {
    "timeout": 60,
    "reconnect_delay": 5,
    "max_retries": 10
  },
  "watchdog_timeout": 90000
}
```

### 4. Deploy to Device

Using [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html):

```bash
# Install mpremote
pip install mpremote

# Deploy all files
./deploy.sh
```

Or manually:

```bash
mpremote connect /dev/ttyUSB0 cp -r lib/ :lib/
mpremote connect /dev/ttyUSB0 cp main.py config.json secrets.json :
```

## Configuration

### config.json Reference

| Field | Description | Default |
|-------|-------------|---------|
| `stops` | Array of stops with DIVA ID and line filters | - |
| `stops[].diva` | Stop DIVA ID (from Wiener Linien API) | - |
| `stops[].lines` | Object mapping line names to directions | - |
| `line_priority` | Display order for lines | `["49", "N49", "U4", "47A", "52"]` |
| `update_interval` | Data refresh interval in seconds | `30` |
| `animation_interval` | Arriving indicator toggle in seconds | `4` |
| `full_refresh_interval` | Partial refreshes before full refresh | `40` |
| `wlan.timeout` | Wi-Fi connection timeout in seconds | `60` |
| `wlan.reconnect_delay` | Delay before reconnection attempt | `5` |
| `watchdog_timeout` | Watchdog timeout in milliseconds | `90000` |

### Line Filters

- Empty array `[]` = all directions
- `["R"]` = outbound only (Richtung)
- `["H"]` = inbound only (Hin)
- `["R", "H"]` = both directions (same as empty)

### Finding DIVA IDs

Use the [Wiener Linien OGD API](https://www.data.gv.at/katalog/dataset/wiener-linien-echtzeitdaten-via-datendrehscheibe-wien) to find DIVA IDs for your stops.

## How It Works

1. **Boot**: Initialize hardware, display, connect to Wi-Fi, sync time via NTP
2. **Main loop** (configurable interval):
   - Check for button presses (HOME = manual refresh)
   - Check Wi-Fi connection, reconnect if needed
   - Fetch departure data from Wiener Linien API
   - Filter by configured lines/directions
   - Sort by priority (preferred lines first)
   - Render to e-paper with partial refresh
   - Draw Wi-Fi status indicator
3. **Animation**: Toggle arriving indicator every 4 seconds
4. **Watchdog**: 90-second timeout prevents hangs

### E-Paper Refresh Strategy

- **Partial refresh**: Used for regular updates (~0.5s, minimal flashing)
- **Full refresh**: Every 40 updates to clear ghosting (~3s, full flash)

### Button Functions

| Button | Action |
|--------|--------|
| HOME   | Force immediate data refresh |
| EXIT   | (Reserved for future use) |

### Status Indicators

- **Signal bars** (bottom-right): Wi-Fi connected
- **X** (bottom-right): Wi-Fi disconnected
- **\*** (bottom-right): Displaying stale/cached data
- **(Xs ago)** (next to time): Data age when stale

## API

The device fetches data directly from the Wiener Linien OGD API:

```
https://www.wienerlinien.at/ogd_realtime/monitor?diva=60201438&diva=60200956
```

The response is transformed and filtered on-device to minimize memory usage.

## Development

### Linting

This project uses [ruff](https://docs.astral.sh/ruff/) for code quality checks:

```bash
pip install -r requirements-dev.txt
ruff check .
```

Linting runs automatically on push/PR to main via GitHub Actions.

## Troubleshooting

### Wi-Fi Connection Failed

- Check `secrets.json` credentials
- Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
- Check signal strength
- Increase `wlan.timeout` in `config.json`

### Memory Errors

- The device runs garbage collection before HTTP requests
- SPIRAM firmware recommended for better memory management
- Reduce `full_refresh_interval` if issues persist

### Display Ghosting

- Decrease `full_refresh_interval` in `config.json`
- Or trigger manual full refresh by power cycling

### Wi-Fi Keeps Disconnecting

- The device automatically reconnects
- Increase `wlan.reconnect_delay` if router needs more time
- Check router logs for connection issues

## License

MIT
