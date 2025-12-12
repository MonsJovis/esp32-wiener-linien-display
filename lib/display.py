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
TEXT_LEFT_OFFSET = 4
LINE_HEIGHT = 42  # Adjusted for new font sizes
TOP_OFFSET = 8
LAST_ROW_TOP_OFFSET = 288

# Display instance
epd = None

# Refresh management
_refresh_count = 0
FULL_REFRESH_INTERVAL = 40  # Do full refresh every N updates to clear ghosting


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
    priority_order = ['49', 'N49', 'U4', '47A', '52']
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

        # Draw destination with 8px built-in font
        towards = line.get('towards', '').split(',')[0] if line.get('towards') else ''

        # Shorten
        if towards.upper() == 'HEILIGENSTADT':
            towards = 'Heiligenst.'

        if towards.upper() == 'ANSCHÜTZGASSE':
            towards = 'Anschützg.'

        if towards.upper() == 'UNTER ST. VEIT U':
            towards = 'Unter St. Veit'

        if towards.upper() == 'WESTBAHNHOF S U':
            towards = 'Westbhf.'

        # Replace German umlauts for better readability on e-paper
        towards = towards.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue').replace('ß', 'ss')

        towards_x = TEXT_LEFT_OFFSET + get_text_width_24(line_name) + 8
        towards_y = pos_y + 8  # Vertically center 8px font within 24px line
        epd.text(towards, towards_x, towards_y, COLOR_BLACK)

        # Draw departure times with 16px bitmap font
        # Position after destination with some spacing
        times_x = towards_x + len(towards) * 8 + 12
        # Vertically center the smaller font relative to line name
        times_y = pos_y + (FONT_24_HEIGHT - FONT_16_HEIGHT) // 2
        draw_text_16(epd, times_x, times_y, times_text, COLOR_BLACK)

        line_index += 1

    # Draw current time (bottom left) and last updated (bottom right)
    datetime_tuple = parse_datetime(timestamp)
    hours = two_digits(datetime_tuple[3])
    minutes = two_digits(datetime_tuple[4])

    # Current time - bottom left (with timezone offset)
    import utime
    from lib.init_wifi import get_timezone_offset
    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_time_text = "{}:{}".format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Last updated - bottom right
    updated_text = "Upd: {}:{}".format(hours, minutes)
    updated_x = DISPLAY_WIDTH - len(updated_text) * 8 - TEXT_LEFT_OFFSET
    epd.text(updated_text, updated_x, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Refresh display - use partial refresh normally, full refresh periodically to clear ghosting
    _refresh_count += 1
    if _refresh_count >= FULL_REFRESH_INTERVAL:
        epd.show()  # Full refresh to clear ghosting
        _refresh_count = 0
    else:
        epd.show_partial()  # Partial refresh - faster, less flashing


# Track last displayed minute to avoid unnecessary updates
_last_displayed_minute = -1


def update_current_time():
    """Update only the current time display. Returns True if display was updated."""
    global epd, _last_displayed_minute

    import utime
    from lib.init_wifi import get_timezone_offset
    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_minute = local_time[4]

    # Only update if minute changed
    if current_minute == _last_displayed_minute:
        return False

    _last_displayed_minute = current_minute

    # Clear just the time area (bottom left)
    # 8x8 font, "HH:MM" = 5 chars = 40px wide
    for y in range(LAST_ROW_TOP_OFFSET, LAST_ROW_TOP_OFFSET + 8):
        for x in range(TEXT_LEFT_OFFSET, TEXT_LEFT_OFFSET + 48):
            epd.pixel(x, y, COLOR_WHITE)

    # Draw new time
    current_time_text = "{}:{}".format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Partial refresh for the time update
    epd.show_partial()
    return True
