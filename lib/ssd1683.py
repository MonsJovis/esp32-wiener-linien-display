"""
SSD1683 E-Paper Display Driver for CrowPanel 4.2" (400x300)
Based on: https://github.com/Lepeshka92/micropython-crowpanel-4.2
"""

from time import sleep_ms
from machine import SPI, Pin
from framebuf import FrameBuffer, MONO_HLSB


class SSD1683(FrameBuffer):
    """
    E-Paper display driver for CrowPanel 4.2" with SSD1683 controller.
    Extends FrameBuffer for easy drawing operations.

    Default pins for CrowPanel ESP32-S3:
        SPI: SCK=12, MOSI=11
        Control: CS=45, DC=46, RST=47, BUSY=48
        Power: PWR=7
    """

    def __init__(self, width=400, height=300, cs=45, dc=46, rst=47, busy=48,
                 pwr=7, spi_id=1, sck=12, mosi=11):
        self._w = width
        self._h = height
        self._buf = bytearray(width * height // 8)
        super().__init__(self._buf, width, height, MONO_HLSB)

        self._cs = Pin(cs, Pin.OUT)
        self._dc = Pin(dc, Pin.OUT)
        self._rst = Pin(rst, Pin.OUT)
        self._busy = Pin(busy, Pin.IN)
        self._pwr = Pin(pwr, Pin.OUT)

        self._spi = SPI(spi_id,
                        baudrate=4_000_000,
                        sck=Pin(sck),
                        mosi=Pin(mosi),
                        firstbit=SPI.MSB)

    def _cmd(self, b):
        """Send command byte"""
        self._cs(0)
        self._dc(0)
        self._spi.write(bytearray([b]))
        self._cs(1)

    def _dat(self, b):
        """Send data byte"""
        self._cs(0)
        self._dc(1)
        self._spi.write(bytearray([b]))
        self._cs(1)

    def _wait(self):
        """Wait for display to be ready (BUSY pin low)"""
        while self._busy.value() == 1:
            sleep_ms(1)

    def _reset(self):
        """Hardware reset sequence"""
        self._rst.value(0)
        sleep_ms(10)
        self._rst.value(1)
        sleep_ms(10)

    def _pos(self, x1, y1, x2, y2):
        """Set RAM address window"""
        self._cmd(0x44)
        self._dat((x1 >> 3) & 0xFF)
        self._dat((x2 >> 3) & 0xFF)

        self._cmd(0x45)
        self._dat(y1 & 0xFF)
        self._dat((y1 >> 8) & 0xFF)
        self._dat(y2 & 0xFF)
        self._dat((y2 >> 8) & 0xFF)

    def _cur(self, x, y):
        """Set cursor position"""
        self._cmd(0x4E)
        self._dat(x & 0xFF)

        self._cmd(0x4F)
        self._dat(y & 0xFF)
        self._dat((y >> 8) & 0xFF)

    def _update(self):
        """Trigger full display refresh (causes flashing)"""
        self._cmd(0x22)
        self._dat(0xF7)  # Full refresh mode
        self._cmd(0x20)
        self._wait()

    def _update_partial(self):
        """Trigger partial display refresh (minimal flashing)"""
        self._cmd(0x22)
        self._dat(0xDC)  # Partial refresh mode
        self._cmd(0x20)
        self._wait()

    def power_on(self):
        """Enable display power"""
        self._pwr.value(1)
        sleep_ms(10)

    def power_off(self):
        """Disable display power"""
        self._pwr.value(0)

    def init(self):
        """Initialize the display"""
        self.power_on()
        self._reset()
        self._wait()

        self._cmd(0x12)  # Software reset
        self._wait()

        self._cmd(0x21)  # Display update control
        self._dat(0x40)
        self._dat(0x00)

        self._cmd(0x3C)  # Border waveform
        self._dat(0x05)

        self._cmd(0x11)  # Data entry mode
        self._dat(0x03)  # X increment, Y increment

        self._pos(0, 0, self._w - 1, self._h - 1)
        self._cur(0, 0)
        self._wait()

    def sleep(self):
        """Put display into deep sleep mode"""
        self._cmd(0x10)
        self._dat(0x01)
        sleep_ms(100)

    def show(self):
        """Write framebuffer to display and do full refresh (flashes)"""
        self._cmd(0x24)  # Write RAM
        self._cs(0)
        self._dc(1)
        self._spi.write(self._buf)
        self._cs(1)
        self._update()

    def show_partial(self):
        """Write framebuffer to display and do partial refresh (minimal flashing)"""
        self._cmd(0x24)  # Write RAM
        self._cs(0)
        self._dc(1)
        self._spi.write(self._buf)
        self._cs(1)
        self._update_partial()

    @property
    def width(self):
        return self._w

    @property
    def height(self):
        return self._h
