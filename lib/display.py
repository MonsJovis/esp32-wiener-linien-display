"""
Display module for CrowPanel 4.2" E-Paper (400x300)
"""

from lib.parse_datetime import parse_datetime
from lib.utils import two_digits
from lib.ssd1683 import SSD1683

DISPLAY_WIDTH = 400
DISPLAY_HEIGHT = 300

# E-Paper colors (MONO_HLSB: 0=black, 1=white)
COLOR_BLACK = 0
COLOR_WHITE = 1

# Layout constants
TEXT_LEFT_OFFSET = 20
LINE_HEIGHT = 40
TOP_OFFSET = 15
LAST_ROW_TOP_OFFSET = 275

# Font scaling (MicroPython framebuf.text uses 8x8 font)
FONT_WIDTH = 8
FONT_HEIGHT = 8

# Display instance
epd = None


def init_display():
    """Initialize the e-paper display"""
    global epd
    epd = SSD1683()
    epd.init()
    epd.fill(COLOR_WHITE)
    epd.show()


def _draw_text_scaled(x, y, text, color, scale=1):
    """
    Draw text with scaling.
    MicroPython's framebuf only supports 8x8 font at 1x scale.
    For larger text, we draw each character multiple times offset.
    """
    global epd
    if scale == 1:
        epd.text(text, x, y, color)
    else:
        # Simple scaling by drawing text multiple times with offsets
        for dy in range(scale):
            for dx in range(scale):
                epd.text(text, x + dx, y + dy, color)


def write_start_msg_to_display(msg="Booting"):
    """Show startup message"""
    global epd
    epd.fill(COLOR_WHITE)
    _draw_text_scaled(TEXT_LEFT_OFFSET, 100, "Starting ...", COLOR_BLACK, 3)
    _draw_text_scaled(TEXT_LEFT_OFFSET, 150, msg, COLOR_BLACK, 2)
    epd.show()


def write_error_to_display(msg="Unknown reason"):
    """Show error message"""
    global epd
    epd.fill(COLOR_WHITE)
    _draw_text_scaled(TEXT_LEFT_OFFSET, 80, "Error", COLOR_BLACK, 4)
    _draw_text_scaled(TEXT_LEFT_OFFSET, 140, msg, COLOR_BLACK, 2)
    epd.show()


def write_fetching_sign_to_display():
    """
    Show fetching indicator.
    Note: For e-paper, we skip this to avoid unnecessary refreshes.
    The full refresh in write_to_display will happen soon anyway.
    """
    pass


def write_to_display(data, timestamp):
    """Render departure data to display"""
    global epd

    epd.fill(COLOR_WHITE)

    line_index = 0

    # Extract all lines from all stops
    lines = [line for stop in data for line in stop['lines']]

    # Sort by priority (preferred lines first)
    priority_order = ['U4', '49', 'N49', '46', 'N46', '47A', '52']
    lines = sorted(
        lines,
        key=lambda line: (
            line['name'] not in priority_order,
            priority_order.index(line['name']) if line['name'] in priority_order else 999,
            line['name']
        )
    )

    for line in lines:
        pos_y = TOP_OFFSET + line_index * LINE_HEIGHT
        line_name = line['name']
        departures = line['departures']

        # Filter U4 departures (need at least 6 min to reach the station)
        if line_name == 'U4':
            departures = [d for d in departures if d['countdown'] >= 6]

        # Format departure times
        times = [str(d['countdown']) + "'" for d in departures[:5]]
        times_text = '  '.join(times)

        # Draw line name (larger, bold effect)
        _draw_text_scaled(TEXT_LEFT_OFFSET, pos_y, line_name, COLOR_BLACK, 3)

        # Draw departure times
        times_x = TEXT_LEFT_OFFSET + len(line_name) * FONT_WIDTH * 3 + 30
        _draw_text_scaled(times_x, pos_y + 4, times_text, COLOR_BLACK, 2)

        line_index += 1

    # Draw timestamp at bottom
    datetime_tuple = parse_datetime(timestamp)
    hours = two_digits(datetime_tuple[3])
    minutes = two_digits(datetime_tuple[4])
    timestamp_text = "Last updated: {}:{}".format(hours, minutes)
    _draw_text_scaled(TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, timestamp_text, COLOR_BLACK, 1)

    # Refresh display
    epd.show()
