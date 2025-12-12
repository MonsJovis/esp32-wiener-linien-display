"""
LED control for CrowPanel ESP32-S3

Note: On CrowPanel 4.2" E-Paper:
  - GPIO 2 is now the HOME button (not an LED)
  - GPIO 41 is the onboard LED
"""

from machine import Pin
from utime import sleep

# CrowPanel ESP32-S3 LED pin
led = Pin(41, Pin.OUT)


def led_on():
    led.on()


def led_off():
    led.off()


def led_error_blink(seconds):
    seconds_passed = 0
    while seconds_passed < seconds:
        led_on()
        sleep(0.1)
        led_off()
        sleep(0.1)
        seconds_passed += 0.2
