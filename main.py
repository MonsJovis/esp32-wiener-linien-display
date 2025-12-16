import utime
from utime import sleep
from lib.display import init_display, write_error_to_display, write_fetching_sign_to_display, write_start_msg_to_display, write_to_display, update_current_time, update_arriving_animation, clear_cached_departures
from lib.init_wifi import init_wifi
from lib.get_data import get_data
from machine import WDT

# Watchdog timer: 90s to account for e-paper refresh time (~3s)
wdt = WDT(timeout=90 * 1000)

def initialize():
    global wdt

    wdt.feed()

    print('Initializing display ...')
    init_display()
    wdt.feed()

    write_start_msg_to_display('Initializing Wi-Fi ...')

    print('Initializing Wi-Fi ...')
    if not init_wifi(wdt):
        print('Wi-Fi connection failed')
        write_error_to_display('Wi-Fi connection failed')
        return False

    print('Wi-Fi connection successful')
    wdt.feed()

    write_start_msg_to_display('Fetching data ...')
    return True

def start_main_loop():
    global wdt

    last_data_fetch = 0
    last_animation_toggle = 0
    has_displayed_data = False  # Track if we've ever shown data successfully
    DATA_REFRESH_INTERVAL = 30  # seconds
    ANIMATION_INTERVAL = 4  # seconds - animation toggle for arriving indicators

    while True:
        wdt.feed()

        current_time = utime.time()

        # Fetch new data every 30 seconds
        if current_time - last_data_fetch >= DATA_REFRESH_INTERVAL:
            wdt.feed()  # Feed watchdog before potentially long HTTP request
            print('Fetching data ...')
            write_fetching_sign_to_display()

            # Clear cached data to free memory before HTTP request
            clear_cached_departures()

            data = None
            try:
                data = get_data()
                wdt.feed()  # Feed watchdog after HTTP request completes
            except Exception as e:
                print(e)

            if data is None:
                print('Error fetching data')
                # Only show error screen if we haven't displayed data yet
                # Otherwise keep showing the last valid data (stale is better than error)
                if not has_displayed_data:
                    write_error_to_display('Error fetching data')
                last_data_fetch = current_time  # Avoid rapid retries
                sleep(1)
                continue

            print('Writing to display ...')
            write_to_display(data['data'])
            wdt.feed()  # Feed watchdog after display update
            has_displayed_data = True
            last_data_fetch = current_time
            last_animation_toggle = current_time  # Reset animation timer after data refresh

        # Toggle arriving indicator animation every 3 seconds
        if has_displayed_data and current_time - last_animation_toggle >= ANIMATION_INTERVAL:
            update_arriving_animation()
            wdt.feed()  # Feed watchdog after animation update
            last_animation_toggle = current_time
        else:
            # Update current time display every second (only refreshes if minute changed)
            update_current_time()

        sleep(1)

def main():
    if initialize():
        start_main_loop()


main()
