import utime
from utime import sleep
from lib.display import init_display, write_error_to_display, write_fetching_sign_to_display, write_start_msg_to_display, write_to_display, update_current_time
from lib.led import led_error_blink, led_off, led_on
from lib.init_wifi import init_wifi
from lib.get_data import get_data
from machine import WDT

# Watchdog timer: 90s to account for e-paper refresh time (~3s)
wdt = WDT(timeout=90 * 1000)

def initialize():
    global wdt

    led_on()
    wdt.feed()

    print('Initializing display ...')
    init_display()
    wdt.feed()

    write_start_msg_to_display('Initializing Wi-Fi ...')

    print('Initializing Wi-Fi ...')
    if not init_wifi(wdt):
        print('Wi-Fi connection failed')
        write_error_to_display('Wi-Fi connection failed')
        led_error_blink(10)
        return False

    print('Wi-Fi connection successful')
    wdt.feed()

    write_start_msg_to_display('Fetching data ...')
    return True

def start_main_loop():
    global wdt

    last_data_fetch = 0
    DATA_REFRESH_INTERVAL = 30  # seconds

    while True:
        wdt.feed()

        current_time = utime.time()

        # Fetch new data every 30 seconds
        if current_time - last_data_fetch >= DATA_REFRESH_INTERVAL:
            led_off()

            print('Fetching data ...')
            write_fetching_sign_to_display()

            data = None
            try:
                data = get_data()
            except Exception as e:
                print(e)

            if data is None:
                print('Error fetching data')
                write_error_to_display('Error fetching data')
                led_error_blink(5)
                last_data_fetch = current_time  # Avoid rapid retries
                sleep(1)
                continue

            print('Writing to display ...')
            write_to_display(data['data'], data['localeTimestamp'])
            last_data_fetch = current_time

        # Update current time display every second (only refreshes if minute changed)
        update_current_time()

        sleep(1)

def main():
    if initialize():
        start_main_loop()


main()
