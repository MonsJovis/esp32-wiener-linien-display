"""
Hardware abstraction layer for CrowPanel 4.2" E-Paper HMI.
Centralizes pin definitions and provides clean API for hardware access.
"""

from machine import Pin

# Display pins (SSD1683)
DISPLAY_WIDTH = 400
DISPLAY_HEIGHT = 300
DISPLAY_PWR = 7
DISPLAY_CS = 45
DISPLAY_DC = 46
DISPLAY_RST = 47
DISPLAY_BUSY = 48
DISPLAY_SPI = 1
DISPLAY_SCK = 12
DISPLAY_MOSI = 11

# Buttons (directly on board)
KEY_HOME = 2
KEY_EXIT = 1

# Rotary encoder buttons
KEY_PREV = 6
KEY_NEXT = 4
KEY_DONE = 5

# Power LED
POWER_LED = 41


class CrowPanel:
    """Hardware abstraction for CrowPanel 4.2" E-Paper display board."""

    def __init__(self):
        self._display = None
        # Initialize button pins as inputs
        self.home = Pin(KEY_HOME, Pin.IN)
        self.exit = Pin(KEY_EXIT, Pin.IN)
        self.prev = Pin(KEY_PREV, Pin.IN)
        self.done = Pin(KEY_DONE, Pin.IN)
        self.next = Pin(KEY_NEXT, Pin.IN)
        # Initialize LED as output
        self.led = Pin(POWER_LED, Pin.OUT)

    def get_display(self):
        """Lazy-initialize and return the e-paper display driver."""
        if self._display is None:
            from lib.ssd1683 import SSD1683
            # Enable display power
            Pin(DISPLAY_PWR, Pin.OUT, value=1)
            self._display = SSD1683()
        return self._display

    def led_on(self):
        """Turn on the power LED."""
        self.led.value(1)

    def led_off(self):
        """Turn off the power LED."""
        self.led.value(0)

    def led_toggle(self):
        """Toggle the power LED state."""
        self.led.value(not self.led.value())

    def is_home_pressed(self):
        """Check if HOME button is pressed (active low)."""
        return self.home.value() == 0

    def is_exit_pressed(self):
        """Check if EXIT button is pressed (active low)."""
        return self.exit.value() == 0

    def is_next_pressed(self):
        """Check if NEXT (rotary) button is pressed (active low)."""
        return self.next.value() == 0

    def is_prev_pressed(self):
        """Check if PREV (rotary) button is pressed (active low)."""
        return self.prev.value() == 0

    def is_done_pressed(self):
        """Check if DONE (rotary center) button is pressed (active low)."""
        return self.done.value() == 0
