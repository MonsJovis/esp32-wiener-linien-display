"""
Timezone and NTP time synchronization module.
Wi-Fi connection is now handled by wifi_manager.py.
"""

import ntptime
import utime
from utime import sleep

NTP_RETRY_ATTEMPTS = 3
NTP_RETRY_DELAY_SEC = 2

# Vienna timezone: CET (UTC+1) / CEST (UTC+2)
TIMEZONE_OFFSET_HOURS = 1  # Base offset (CET)


def is_dst():
    """Check if daylight saving time is active (last Sunday of March to last Sunday of October).

    DST transitions at 2:00 AM local time:
    - March: clocks move forward (2:00 -> 3:00)
    - October: clocks move back (3:00 -> 2:00)
    """
    now = utime.localtime()
    year, month, day, hour = now[0], now[1], now[2], now[3]

    if month < 3 or month > 10:
        return False
    if month > 3 and month < 10:
        return True

    # Find last Sunday of the month (both March and October have 31 days)
    last_day = 31
    # Get weekday of last day (0=Monday, 6=Sunday)
    last_day_weekday = utime.localtime(utime.mktime((year, month, last_day, 0, 0, 0, 0, 0)))[6]
    last_sunday = last_day - ((last_day_weekday + 1) % 7)

    if month == 3:
        # DST starts: on last Sunday, DST active from 2:00 onwards
        if day > last_sunday:
            return True
        if day == last_sunday:
            return hour >= 2
        return False
    else:  # October
        # DST ends: on last Sunday, DST inactive from 3:00 onwards
        if day < last_sunday:
            return True
        if day == last_sunday:
            return hour < 3
        return False


def get_timezone_offset():
    """Get current timezone offset in seconds (handles DST)."""
    offset_hours = TIMEZONE_OFFSET_HOURS + (1 if is_dst() else 0)
    return offset_hours * 3600


def sync_time():
    """Sync time via NTP with retry logic. Returns True on success."""
    for attempt in range(NTP_RETRY_ATTEMPTS):
        try:
            ntptime.settime()
            print('NTP time sync successful')
            return True
        except Exception as e:
            print('NTP time sync failed (attempt {}/{}):'.format(attempt + 1, NTP_RETRY_ATTEMPTS), e)
            if attempt < NTP_RETRY_ATTEMPTS - 1:
                sleep(NTP_RETRY_DELAY_SEC)
    return False
