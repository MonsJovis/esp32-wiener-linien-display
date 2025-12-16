"""
Display module for CrowPanel 4.2" E-Paper (400x300)
"""

import utime
from lib.utils import two_digits
from lib.ssd1683 import SSD1683
from lib.fonts import draw_text_24, draw_text_16, FONT_24_HEIGHT, FONT_16_HEIGHT
from lib.init_wifi import get_timezone_offset

DISPLAY_WIDTH = 400
DISPLAY_HEIGHT = 300

# E-Paper colors (MONO_HLSB: 0=black, 1=white)
COLOR_BLACK = 0
COLOR_WHITE = 1

# Layout constants
TEXT_LEFT_OFFSET = 8
LINE_NAME_WIDTH = 52  # Fixed width for line name column (e.g., "49", "U4", "47A")
DESTINATION_X = 70  # X position for destination text
TIMES_COLUMN_X = 190  # Fixed X position where departure times start
TIME_SLOT_WIDTH = 52  # Width per time slot - wider for better readability

# Row heights for grouped layout
GROUP_FIRST_ROW_HEIGHT = 34  # First row of group (with line name)
GROUP_SUB_ROW_HEIGHT = 28  # Subsequent rows (destination only)
GROUP_SEPARATOR_PADDING = 6  # Padding above and below separator line
TOP_OFFSET = 4
LAST_ROW_TOP_OFFSET = 288

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


def _shorten_destination(towards):
    """Shorten and normalize destination names for display."""
    if not towards:
        return ''

    # Take first part before comma
    towards = towards.split(',')[0].strip()

    # Shorten known long names
    shortnames = {
        'HEILIGENSTADT': 'Heiligenst.',
        'ANSCHÜTZGASSE': 'Anschuetzg.',
        'UNTER ST. VEIT U': 'Unter St. V.',
        'WESTBAHNHOF S U': 'Westbahnhof',
        'HÜTTELDORF': 'Hütteldorf',
        'KLINIK PENZING': 'Kl. Penzing',
        'URBAN LORITZ PLATZ': 'U. Loritz Pl.',
    }

    upper = towards.upper()
    if upper in shortnames:
        towards = shortnames[upper]

    # Replace German umlauts
    towards = towards.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
    towards = towards.replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue').replace('ß', 'ss')

    return towards


def _draw_separator_line(y):
    """Draw a thin horizontal separator line."""
    epd.hline(TEXT_LEFT_OFFSET, y, DISPLAY_WIDTH - 2 * TEXT_LEFT_OFFSET, COLOR_BLACK)


def write_to_display(data):
    """Render departure data to display with grouped layout by line."""
    global epd, _refresh_count

    epd.fill(COLOR_WHITE)

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

    # Group lines by name
    grouped = {}
    for line in lines:
        name = line['name']
        if name not in grouped:
            grouped[name] = []
        grouped[name].append(line)

    # Maintain priority order for groups
    group_order = []
    seen = set()
    for line in lines:
        if line['name'] not in seen:
            group_order.append(line['name'])
            seen.add(line['name'])

    # Render grouped layout
    current_y = TOP_OFFSET

    for group_idx, line_name in enumerate(group_order):
        group_lines = grouped[line_name]

        # Draw separator line before group (except first)
        if group_idx > 0:
            current_y += GROUP_SEPARATOR_PADDING
            _draw_separator_line(current_y)
            current_y += GROUP_SEPARATOR_PADDING + 1  # +1 for line thickness

        for row_idx, line in enumerate(group_lines):
            departures = line['departures']

            # Filter U4 departures (need at least 6 min to reach station)
            if line_name == 'U4':
                departures = [d for d in departures if d['countdown'] >= 6]

            is_first_row = (row_idx == 0)
            row_height = GROUP_FIRST_ROW_HEIGHT if is_first_row else GROUP_SUB_ROW_HEIGHT

            # Draw line name only on first row of group
            if is_first_row:
                name_y = current_y + (row_height - FONT_24_HEIGHT) // 2
                draw_text_24(epd, TEXT_LEFT_OFFSET, name_y, line_name, COLOR_BLACK)

            # Draw destination
            towards = _shorten_destination(line.get('towards', ''))
            dest_y = current_y + (row_height - BUILTIN_FONT_HEIGHT) // 2
            epd.text(towards, DESTINATION_X, dest_y, COLOR_BLACK)

            # Draw departure times in fixed columns
            times_y = current_y + (row_height - FONT_16_HEIGHT) // 2
            for i, dep in enumerate(departures[:4]):  # Max 4 times
                countdown = dep['countdown']

                # Calculate x position for this time slot
                time_x = TIMES_COLUMN_X + i * TIME_SLOT_WIDTH

                if countdown == 0:
                    # Show dot for arriving (like Wiener Linien displays)
                    time_x += 16  # Center the dot in the slot
                    draw_text_16(epd, time_x, times_y, '.', COLOR_BLACK)
                else:
                    time_str = str(countdown) + "'"
                    # Right-align within slot: pad single digits
                    if countdown < 10:
                        time_x += 12  # Offset for single digit
                    draw_text_16(epd, time_x, times_y, time_str, COLOR_BLACK)

            current_y += row_height

    # Store the update time for "updated X seconds ago" display
    global _last_update_time
    _last_update_time = utime.time()

    # Draw current time (bottom left)
    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_time_text = '{}:{}'.format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Refresh display - use partial refresh normally, full refresh periodically
    _refresh_count += 1
    if _refresh_count >= FULL_REFRESH_INTERVAL:
        epd.show()  # Full refresh to clear ghosting
        _refresh_count = 0
    else:
        epd.show_partial()


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
