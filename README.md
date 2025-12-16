# ESP32 Public Transport Departure Display

Real-time public transport departure display for Vienna (Wiener Linien) running on an ESP32-S3 with a 4.2" e-paper screen.

![MicroPython](https://img.shields.io/badge/MicroPython-1.24-blue)
![ESP32-S3](https://img.shields.io/badge/ESP32--S3-CrowPanel%204.2%22-green)

## Features

- Real-time departure data from Wiener Linien API
- 30-second automatic refresh cycle
- E-paper display with partial refresh (minimal flashing)
- Animated "arriving" indicator for imminent departures
- Grouped display by line with multiple destinations
- Configurable line/direction filters
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

## Project Structure

```
├── main.py              # Entry point, main loop
├── boot.py              # MicroPython boot (empty)
├── secrets.json         # Wi-Fi credentials (not in git)
├── deploy.sh            # Deployment script
└── lib/
    ├── display.py       # E-paper rendering
    ├── fonts.py         # Bitmap fonts (24px, 16px)
    ├── ssd1683.py       # SSD1683 display driver
    ├── get_data.py      # API fetching and filtering
    ├── init_wifi.py     # Wi-Fi connection
    ├── parse_datetime.py# ISO 8601 parsing
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

### 3. Deploy to Device

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
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 cp secrets.json :secrets.json
```

## Configuration

### Monitored Lines

Edit [lib/get_data.py](lib/get_data.py) to configure which stops and lines to monitor:

```python
# DIVA IDs for stops to monitor
DIVA_IDS = ['60201438', '60200956', '60200113']

# Filter configuration: {diva: {line_name: [directions]}}
# Empty direction list means all directions
# Direction values: 'R' (outbound), 'H' (inbound)
LINE_FILTERS = {
    '60201438': {
        '49': [],           # All directions
        'N49': ['R'],       # Only outbound
        '47A': [],          # All directions
    },
    '60200956': {
        'U4': ['H'],        # Only inbound
    },
    '60200113': {
        '52': ['R'],        # Only outbound
    },
}
```

Find DIVA IDs using the [Wiener Linien OGD API](https://www.data.gv.at/katalog/dataset/wiener-linien-echtzeitdaten-via-datendrehscheibe-wien).

### Display Settings

Edit [lib/display.py](lib/display.py) to adjust:

- `FULL_REFRESH_INTERVAL`: Number of partial refreshes before full refresh (default: 40)
- Line priority order in `write_to_display()`
- Destination abbreviations in `_shorten_destination()`

## How It Works

1. **Boot**: Initialize display, connect to Wi-Fi
2. **Main loop** (every 30s):
   - Fetch departure data from Wiener Linien API
   - Filter by configured lines/directions
   - Sort by priority (preferred lines first)
   - Render to e-paper with partial refresh
3. **Animation**: Toggle arriving indicator every 4 seconds
4. **Watchdog**: 90-second timeout prevents hangs

### E-Paper Refresh Strategy

- **Partial refresh**: Used for regular updates (~0.5s, minimal flashing)
- **Full refresh**: Every 40 updates to clear ghosting (~3s, full flash)

## API

The device fetches data directly from the Wiener Linien OGD API:

```
https://www.wienerlinien.at/ogd_realtime/monitor?diva=60201438&diva=60200956
```

The response is transformed and filtered on-device to minimize memory usage.

## Troubleshooting

### Wi-Fi Connection Failed

- Check `secrets.json` credentials
- Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
- Check signal strength

### Memory Errors

- The device runs garbage collection before HTTP requests
- SPIRAM firmware recommended for better memory management
- Reduce `FULL_REFRESH_INTERVAL` if issues persist

### Display Ghosting

- Increase refresh frequency by lowering `FULL_REFRESH_INTERVAL`
- Or trigger manual full refresh by power cycling

## License

MIT
