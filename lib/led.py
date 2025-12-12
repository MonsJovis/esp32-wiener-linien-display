from machine import Pin
from utime import sleep

led = Pin(2, Pin.OUT)

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
