"""
Wi-Fi connection manager with reconnection support.
Provides a class-based API for Wi-Fi operations with watchdog integration.
"""

import network
import utime
from machine import idle


class WLANManager:
    """Manages Wi-Fi connection with automatic reconnection support."""

    def __init__(self, ssid, password, timeout=60, wdt=None):
        """
        Initialize Wi-Fi manager.

        Args:
            ssid: Wi-Fi network name
            password: Wi-Fi password
            timeout: Connection timeout in seconds
            wdt: Optional watchdog timer to feed during connection
        """
        self.ssid = ssid
        self.password = password
        self.timeout = timeout
        self.wdt = wdt
        self.wlan = network.WLAN(network.STA_IF)

    def connect(self):
        """
        Connect to Wi-Fi network.

        Returns:
            True if connected successfully, False on timeout.
        """
        print('Connecting to Wi-Fi:', self.ssid)

        # Reset interface for clean state
        self.wlan.active(False)
        utime.sleep(1)
        self.wlan.active(True)

        # Check if already connected
        if self.wlan.isconnected():
            print('Already connected, IP:', self.wlan.ifconfig()[0])
            return True

        # Initiate connection
        self.wlan.connect(self.ssid, self.password)

        # Wait for connection with timeout
        start = utime.time()
        while not self.wlan.isconnected():
            if utime.time() - start > self.timeout:
                print('Wi-Fi connection timeout')
                return False
            if self.wdt:
                self.wdt.feed()
            elapsed = int(utime.time() - start)
            print('Waiting for connection... {}s'.format(elapsed), end='\r')
            idle()

        print('Connected! IP:', self.wlan.ifconfig()[0])
        return True

    def disconnect(self):
        """Disconnect from Wi-Fi and deactivate interface."""
        if self.wlan.isconnected():
            self.wlan.disconnect()
        self.wlan.active(False)

    def is_connected(self):
        """Check if currently connected to Wi-Fi."""
        return self.wlan.isconnected()

    def get_ip(self):
        """Get current IP address, or None if not connected."""
        if self.wlan.isconnected():
            return self.wlan.ifconfig()[0]
        return None

    def reconnect(self, delay=5):
        """
        Reconnect to Wi-Fi with a delay.

        Args:
            delay: Seconds to wait before reconnecting

        Returns:
            True if reconnected successfully, False otherwise.
        """
        print('Reconnecting to Wi-Fi...')
        self.disconnect()
        utime.sleep(delay)
        return self.connect()
