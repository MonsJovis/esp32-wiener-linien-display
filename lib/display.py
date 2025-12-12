"""
Display module for CrowPanel 4.2" E-Paper (400x300)
"""

from lib.parse_datetime import parse_datetime
from lib.utils import two_digits
from lib.ssd1683 import SSD1683
from lib.fonts import draw_text_24, draw_text_16, get_text_width_24, FONT_24_HEIGHT, FONT_16_HEIGHT

DISPLAY_WIDTH = 400
DISPLAY_HEIGHT = 300

# E-Paper colors (MONO_HLSB: 0=black, 1=white)
COLOR_BLACK = 0
COLOR_WHITE = 1

# Layout constants
TEXT_LEFT_OFFSET = 20
LINE_HEIGHT = 36  # Adjusted for new font sizes
TOP_OFFSET = 12
LAST_ROW_TOP_OFFSET = 280

# Display instance
epd = None

# Refresh management
_refresh_count = 0
FULL_REFRESH_INTERVAL = 10  # Do full refresh every N updates to clear ghosting


def init_display():
    """Initialize the e-paper display"""
    global epd, _refresh_count
    epd = SSD1683()
    epd.init()
    epd.fill(COLOR_WHITE)
    # Single full refresh on startup to ensure clean slate
    epd.show()
    _refresh_count = 0


def write_start_msg_to_display(msg="Booting"):
    """Show startup message - uses partial refresh to reduce flashing"""
    global epd
    epd.fill(COLOR_WHITE)
    # Use built-in font for startup messages (simple, readable)
    epd.text("Starting ...", TEXT_LEFT_OFFSET, 100, COLOR_BLACK)
    epd.text(msg, TEXT_LEFT_OFFSET, 120, COLOR_BLACK)
    epd.show_partial()


def write_error_to_display(msg="Unknown reason"):
    """Show error message - uses full refresh to ensure visibility"""
    global epd, _refresh_count
    epd.fill(COLOR_WHITE)
    # Use built-in font for error messages
    epd.text("ERROR", TEXT_LEFT_OFFSET, 80, COLOR_BLACK)
    epd.text(msg, TEXT_LEFT_OFFSET, 100, COLOR_BLACK)
    epd.show()  # Full refresh for errors to clear any ghosting
    _refresh_count = 0


def write_fetching_sign_to_display():
    """
    Show fetching indicator.
    Note: For e-paper, we skip this to avoid unnecessary refreshes.
    The full refresh in write_to_display will happen soon anyway.
    """
    pass


def write_to_display(data, timestamp):
    """Render departure data to display - uses partial refresh with periodic full refresh"""
    global epd, _refresh_count

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

        # Draw line name with 24px bitmap font
        draw_text_24(epd, TEXT_LEFT_OFFSET, pos_y, line_name, COLOR_BLACK)

        # Draw departure times with 16px bitmap font
        # Position after line name with some spacing
        times_x = TEXT_LEFT_OFFSET + get_text_width_24(line_name) + 20
        # Vertically center the smaller font relative to line name
        times_y = pos_y + (FONT_24_HEIGHT - FONT_16_HEIGHT) // 2
        draw_text_16(epd, times_x, times_y, times_text, COLOR_BLACK)

        line_index += 1

    # Draw timestamp at bottom (using built-in 8x8 font - user said it looks fine)
    datetime_tuple = parse_datetime(timestamp)
    hours = two_digits(datetime_tuple[3])
    minutes = two_digits(datetime_tuple[4])
    timestamp_text = "Last updated: {}:{}".format(hours, minutes)
    epd.text(timestamp_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Refresh display - use partial refresh normally, full refresh periodically to clear ghosting
    _refresh_count += 1
    if _refresh_count >= FULL_REFRESH_INTERVAL:
        epd.show()  # Full refresh to clear ghosting
        _refresh_count = 0
    else:
        epd.show_partial()  # Partial refresh - faster, less flashing
