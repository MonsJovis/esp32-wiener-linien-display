"""
Display module for CrowPanel 4.2" E-Paper (400x300)
"""

import utime
from lib.utils import two_digits
from lib.ssd1683 import SSD1683
from lib.fonts import draw_text_24, draw_text_16, get_text_width_24, FONT_24_HEIGHT, FONT_16_HEIGHT
from lib.init_wifi import get_timezone_offset

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
TIMES_COLUMN_X = 192  # Fixed X position where departure times start (table alignment)

# Font sizes for built-in 8px font
BUILTIN_FONT_HEIGHT = 8
BUILTIN_FONT_WIDTH = 8
TIME_DISPLAY_WIDTH = 5 * BUILTIN_FONT_WIDTH + 8  # "HH:MM" = 5 chars + padding

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


def _draw_centered_text(text, y):
    """Draw text horizontally centered on the display."""
    text_width = len(text) * BUILTIN_FONT_WIDTH
    x = (DISPLAY_WIDTH - text_width) // 2
    epd.text(text, x, y, COLOR_BLACK)


def _draw_boot_frame():
    """Draw a decorative frame for boot/status screens."""
    # Outer border
    margin = 20
    epd.rect(margin, margin, DISPLAY_WIDTH - 2 * margin, DISPLAY_HEIGHT - 2 * margin, COLOR_BLACK)
    # Inner border (double-line effect)
    epd.rect(margin + 3, margin + 3, DISPLAY_WIDTH - 2 * margin - 6, DISPLAY_HEIGHT - 2 * margin - 6, COLOR_BLACK)

    # Top decorative line
    line_y = 70
    epd.hline(margin + 20, line_y, DISPLAY_WIDTH - 2 * margin - 40, COLOR_BLACK)

    # Bottom decorative line
    line_y = DISPLAY_HEIGHT - 90
    epd.hline(margin + 20, line_y, DISPLAY_WIDTH - 2 * margin - 40, COLOR_BLACK)


def write_start_msg_to_display(msg="Booting"):
    """Show startup message with centered layout - uses partial refresh to reduce flashing"""
    global epd
    epd.fill(COLOR_WHITE)

    _draw_boot_frame()

    # Title
    _draw_centered_text("WIENER LINIEN", 90)
    _draw_centered_text("Departure Monitor", 110)

    # Status message
    _draw_centered_text(msg, 150)

    # Loading indicator dots
    _draw_centered_text("...", 170)

    # Footer
    _draw_centered_text("Vienna Public Transport", DISPLAY_HEIGHT - 70)

    epd.show_partial()


def write_error_to_display(msg="Unknown reason"):
    """Show error message with centered layout - uses full refresh to ensure visibility"""
    global epd, _refresh_count
    epd.fill(COLOR_WHITE)

    _draw_boot_frame()

    # Error title with warning indicators
    _draw_centered_text("! ! !  ERROR  ! ! !", 90)

    # Horizontal separator
    epd.hline(60, 115, DISPLAY_WIDTH - 120, COLOR_BLACK)

    # Error message
    _draw_centered_text(msg, 140)

    # Instructions
    _draw_centered_text("Check connection and", 180)
    _draw_centered_text("restart device", 200)

    epd.show()  # Full refresh for errors to clear any ghosting
    _refresh_count = 0


def write_fetching_sign_to_display():
    """
    Show fetching indicator.
    Note: For e-paper, we skip this to avoid unnecessary refreshes.
    The full refresh in write_to_display will happen soon anyway.
    """
    pass


def write_to_display(data):
    """Render departure data to display - uses partial refresh with periodic full refresh"""
    global epd, _refresh_count

    epd.fill(COLOR_WHITE)

    line_index = 0

    # Extract all lines from all stops
    lines = [line for stop in data for line in stop['lines']]

    # Sort by priority (preferred lines first), then by direction (R before H)
    priority_order = ['49', 'N49', 'U4', '47A', '52']
    lines = sorted(
        lines,
        key=lambda line: (
            line['name'] not in priority_order,
            priority_order.index(line['name']) if line['name'] in priority_order else 999,
            line.get('direction', '') != 'R',  # R comes first
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

        # Format departure times (right-pad single digits for alignment)
        times = []
        for d in departures[:5]:
            t = str(d['countdown']) + "'"
            # Pad single-digit times with trailing space for consistent width
            if d['countdown'] < 10:
                t = ' ' + t  # Leading space for single digits
            times.append(t)
        times_text = '  '.join(times)

        # Draw line name with 24px bitmap font
        draw_text_24(epd, TEXT_LEFT_OFFSET, pos_y, line_name, COLOR_BLACK)

        # Draw destination with 8px built-in font
        towards = line.get('towards', '').split(',')[0].strip() if line.get('towards') else ''

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
        # Fixed column position for table alignment
        times_x = TIMES_COLUMN_X
        # Vertically center the smaller font relative to line name
        times_y = pos_y + (FONT_24_HEIGHT - FONT_16_HEIGHT) // 2
        draw_text_16(epd, times_x, times_y, times_text, COLOR_BLACK)

        line_index += 1

    # Store the update time for "updated X seconds ago" display
    global _last_update_time
    _last_update_time = utime.time()

    # Draw current time (bottom left)
    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_time_text = '{}:{}'.format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Bottom right: leave empty initially (will show "updated X sec ago" after 20s)

    # Refresh display - use partial refresh normally, full refresh periodically to clear ghosting
    _refresh_count += 1
    if _refresh_count >= FULL_REFRESH_INTERVAL:
        epd.show()  # Full refresh to clear ghosting
        _refresh_count = 0
    else:
        epd.show_partial()  # Partial refresh - faster, less flashing


# Track last displayed minute to avoid unnecessary updates
_last_displayed_minute = -1

# Track last data update timestamp for "updated X seconds ago" display
_last_update_time = 0


# Width reserved for "updated X sec ago" text (max ~18 chars)
UPDATED_TEXT_MAX_WIDTH = 18 * BUILTIN_FONT_WIDTH

# Track last displayed "seconds ago" to avoid unnecessary refreshes
_last_displayed_seconds_ago = -1


def update_current_time():
    """Update current time and 'updated X sec ago' display. Returns True if display was updated."""
    global epd, _last_displayed_minute, _last_update_time, _last_displayed_seconds_ago

    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_minute = local_time[4]

    # Calculate seconds since last data update
    seconds_ago = utime.time() - _last_update_time if _last_update_time > 0 else 0

    # Determine if we need to update the "X sec ago" display (only after 31s, update every 5s)
    should_show_seconds_ago = seconds_ago > 31
    seconds_ago_bucket = (seconds_ago // 5) * 5 if should_show_seconds_ago else -1

    # Check if anything needs updating
    minute_changed = current_minute != _last_displayed_minute
    seconds_display_changed = seconds_ago_bucket != _last_displayed_seconds_ago

    if not minute_changed and not seconds_display_changed:
        return False

    # Clear the bottom row
    epd.fill_rect(TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, DISPLAY_WIDTH - 2 * TEXT_LEFT_OFFSET, BUILTIN_FONT_HEIGHT, COLOR_WHITE)

    # Draw current time (bottom left)
    current_time_text = '{}:{}'.format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Draw "updated X sec ago" (bottom right) only if > 20 seconds
    if should_show_seconds_ago:
        updated_text = 'updated {} sec ago'.format(seconds_ago_bucket)
        updated_x = DISPLAY_WIDTH - len(updated_text) * BUILTIN_FONT_WIDTH - TEXT_LEFT_OFFSET
        epd.text(updated_text, updated_x, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    _last_displayed_minute = current_minute
    _last_displayed_seconds_ago = seconds_ago_bucket

    # Partial refresh for the update
    epd.show_partial()
    return True
