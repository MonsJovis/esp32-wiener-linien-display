import network
import ntptime
import utime
from utime import sleep
from lib.secrets import get_wifi_secrets

WIFI_CONNECTION_ATTEMPTS = 10
WIFI_CONNECTION_RETRY_WAIT_SEC = 1

# Vienna timezone: CET (UTC+1) / CEST (UTC+2)
TIMEZONE_OFFSET_HOURS = 1  # Base offset (CET)


def is_dst():
    """Check if daylight saving time is active (last Sunday of March to last Sunday of October)."""
    now = utime.localtime()
    year, month, day = now[0], now[1], now[2]

    if month < 3 or month > 10:
        return False
    if month > 3 and month < 10:
        return True

    # Find last Sunday of the month
    # Day 31 for March, 31 for October
    last_day = 31
    # Get weekday of last day (0=Monday, 6=Sunday)
    last_day_weekday = utime.localtime(utime.mktime((year, month, last_day, 0, 0, 0, 0, 0)))[6]
    last_sunday = last_day - ((last_day_weekday + 1) % 7)

    if month == 3:
        return day >= last_sunday
    else:  # October
        return day < last_sunday


def get_timezone_offset():
    """Get current timezone offset in seconds (handles DST)."""
    offset_hours = TIMEZONE_OFFSET_HOURS + (1 if is_dst() else 0)
    return offset_hours * 3600


def sync_time():
    """Sync time via NTP. Returns True on success."""
    try:
        ntptime.settime()
        print('NTP time sync successful')
        return True
    except Exception as e:
        print('NTP time sync failed:', e)
        return False

def init_wifi():
    # Get Wi-Fi credentials
    secrets = get_wifi_secrets()

    wlan = network.WLAN(network.STA_IF)

    # Try to connect to the network (max 10 attempts)
    for _ in range(WIFI_CONNECTION_ATTEMPTS):
        # Activate the network interface
        wlan.active(True)

        # Connect to your network
        try:
            wlan.connect(secrets[0], secrets[1])
        except Exception as e:
            print('Error while connecting to Wi-Fi')
            print(e)

        if wlan.isconnected():
            # Sync time via NTP after successful connection
            sync_time()
            return True

        print("Not connected to Wi-Fi yet. Trying again in {} second ...'".format(WIFI_CONNECTION_RETRY_WAIT_SEC))
        sleep(WIFI_CONNECTION_RETRY_WAIT_SEC)

    return False