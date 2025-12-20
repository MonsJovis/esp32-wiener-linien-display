"""
Main entry point for ESP32 Wiener Linien departure display.
"""

import utime
import machine
from machine import WDT

from lib.config import get_update_interval, get_animation_interval, get_wlan_config, get_watchdog_timeout, get_stale_restart_threshold
from lib.crowpanel import CrowPanel
from lib.wifi_manager import WLANManager
from lib.secrets import get_wifi_secrets
from lib.display import (
    init_display, write_error_to_display, write_start_msg_to_display,
    write_to_display, update_current_time, update_arriving_animation,
    clear_cached_departures, draw_wifi_status
)
from lib.get_data import get_data
from lib.init_wifi import sync_time

# Global instances
panel = None
wlan = None
wdt = None


def initialize():
    """Initialize hardware, display, and Wi-Fi connection."""
    global panel, wlan, wdt

    # Initialize watchdog timer
    wdt = WDT(timeout=get_watchdog_timeout())
    wdt.feed()

    # Initialize hardware abstraction
    panel = CrowPanel()

    # Initialize display
    print('Initializing display...')
    init_display()
    wdt.feed()

    write_start_msg_to_display('Connecting to Wi-Fi...')

    # Initialize Wi-Fi manager
    secrets = get_wifi_secrets()
    wlan_config = get_wlan_config()
    wlan = WLANManager(
        ssid=secrets[0],
        password=secrets[1],
        timeout=wlan_config['timeout_sec'],
        wdt=wdt
    )

    print('Connecting to Wi-Fi...')
    if not wlan.connect():
        print('Wi-Fi connection failed')
        write_error_to_display('Wi-Fi connection failed')
        return False

    print('Wi-Fi connected')
    wdt.feed()

    # Sync time via NTP
    write_start_msg_to_display('Syncing time...')
    sync_time()
    wdt.feed()

    write_start_msg_to_display('Fetching data...')
    return True


def check_buttons():
    """
    Check for button presses and return action string.

    Returns:
        'refresh' if HOME button pressed (force data refresh)
        'toggle_display' if EXIT button pressed
        None if no button pressed
    """
    if panel.is_home_pressed():
        return 'refresh'
    if panel.is_exit_pressed():
        return 'toggle_display'
    return None


def start_main_loop():
    """Main polling loop for data fetching and display updates."""
    global wdt, wlan

    last_data_fetch = 0
    last_animation_toggle = 0
    has_displayed_data = False
    using_stale_data = False

    DATA_REFRESH_INTERVAL = get_update_interval()
    ANIMATION_INTERVAL = get_animation_interval()
    STALE_RESTART_THRESHOLD = get_stale_restart_threshold()

    while True:
        wdt.feed()
        current_time = utime.time()

        # Check for button input
        action = check_buttons()
        if action == 'refresh':
            print('Manual refresh requested')
            last_data_fetch = 0  # Force immediate refresh
            utime.sleep_ms(200)  # Debounce

        # Check Wi-Fi and reconnect if needed
        if not wlan.is_connected():
            print('Wi-Fi disconnected, reconnecting...')
            wlan_config = get_wlan_config()
            if not wlan.reconnect(delay=wlan_config['reconnect_delay_sec']):
                print('Reconnection failed')
                using_stale_data = True
                panel.led_on()
            else:
                print('Reconnected successfully')

        # Fetch new data at interval
        if current_time - last_data_fetch >= DATA_REFRESH_INTERVAL:
            wdt.feed()
            print('Fetching data...')

            # Clear cached data to free memory before HTTP request
            clear_cached_departures()

            data = None
            try:
                data = get_data()
                wdt.feed()
            except Exception as e:
                print('Error fetching data:', e)

            if data is None:
                print('Error: No data returned')
                # Only show error screen if we haven't displayed data yet
                # Otherwise keep showing last valid data (stale is better than error)
                if not has_displayed_data:
                    write_error_to_display('Error fetching data')
                using_stale_data = True
                panel.led_on()
                last_data_fetch = current_time
                utime.sleep(1)
                continue

            print('Writing to display...')
            write_to_display(data['data'])
            draw_wifi_status(wlan.is_connected(), using_stale_data)
            wdt.feed()

            has_displayed_data = True
            using_stale_data = False
            panel.led_off()
            last_data_fetch = current_time
            last_animation_toggle = current_time

        # Check if stale for too long - trigger restart
        if using_stale_data and (current_time - last_data_fetch) > STALE_RESTART_THRESHOLD:
            print('Stale for {}s, restarting...'.format(current_time - last_data_fetch))
            machine.reset()

        # Toggle arriving indicator animation at interval
        if has_displayed_data and current_time - last_animation_toggle >= ANIMATION_INTERVAL:
            update_arriving_animation()
            last_animation_toggle = current_time
        else:
            # Update current time display (only refreshes if minute changed)
            update_current_time()

        # Sleep for 1 second
        # Note: Using time.sleep instead of machine.lightsleep to ensure
        # watchdog compatibility - lightsleep can cause watchdog resets
        utime.sleep(1)


def main():
    """Entry point."""
    if initialize():
        start_main_loop()


main()
