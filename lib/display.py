"""
Display module for CrowPanel 4.2" E-Paper (400x300)
"""

import utime
import gc
from lib.utils import two_digits
from lib.ssd1683 import SSD1683
from lib.fonts import draw_text_24, draw_text_16, FONT_24_HEIGHT, FONT_16_HEIGHT
from lib.init_wifi import get_timezone_offset
from lib.config import get_full_refresh_interval, get_line_priority

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

# Animation state for arriving indicator
_arriving_indicator_state = False  # False=bottom-left, True=top-right

# Cached departure data for animation redraws
_cached_departures = None

# Wi-Fi status state (for redrawing after display updates)
_wifi_connected = False
_wifi_stale_data = False


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
    global epd, _refresh_count, _cached_departures

    print('write_to_display: starting render, animation_state={}'.format(_arriving_indicator_state))

    # Cache the data for animation redraws
    _cached_departures = data

    epd.fill(COLOR_WHITE)

    # Extract all lines from all stops
    lines = [line for stop in data for line in stop['lines']]

    # Sort by priority (preferred lines first), then by direction (R before H)
    priority_order = get_line_priority()
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
                    # Animated square for arriving (alternates bottom-left / top-right)
                    square_size = 8  # 8x8 square
                    if _arriving_indicator_state:
                        # Top-right position (8px offset on x axis)
                        epd.fill_rect(time_x + 8, times_y, square_size, square_size, COLOR_BLACK)
                    else:
                        # Bottom-left position
                        epd.fill_rect(time_x, times_y + FONT_16_HEIGHT - square_size, square_size, square_size, COLOR_BLACK)
                else:
                    time_str = str(countdown) + "'"
                    # Right-align within slot: pad single digits
                    if countdown < 10:
                        time_x += 12  # Offset for single digit
                    draw_text_16(epd, time_x, times_y, time_str, COLOR_BLACK)

            current_y += row_height

    # Store the update time for stale indicator
    global _last_update_time
    _last_update_time = utime.time()

    # Draw current time (bottom left)
    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_time_text = '{}:{}'.format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Draw stale indicator (center) if data is stale
    _draw_stale_indicator()

    # Draw Wi-Fi status (bottom right) - uses cached state
    _draw_wifi_status_internal()

    # Refresh display - use partial refresh normally, full refresh periodically
    _refresh_count += 1
    full_refresh_interval = get_full_refresh_interval()
    if _refresh_count >= full_refresh_interval:
        print('write_to_display: full refresh (count={})'.format(_refresh_count))
        epd.show()  # Full refresh to clear ghosting
        _refresh_count = 0
    else:
        print('write_to_display: partial refresh (count={})'.format(_refresh_count))
        epd.show_partial()

    # Free memory after display refresh to help with TLS allocation
    gc.collect()


def clear_cached_departures():
    """Clear cached departure data to free memory."""
    global _cached_departures
    _cached_departures = None
    gc.collect()


def _draw_stale_indicator():
    """
    Draw centered stale data warning with triangle icon and elapsed time.
    Called internally by display update functions.
    """
    global epd, _wifi_stale_data, _last_update_time

    center_x = DISPLAY_WIDTH // 2
    y = LAST_ROW_TOP_OFFSET

    # Calculate seconds since last update
    seconds_ago = utime.time() - _last_update_time if _last_update_time > 0 else 0

    # Build the text: "STALE Xs" where X is seconds
    stale_text = 'STALE {}s'.format(seconds_ago) if _wifi_stale_data else ''

    # Calculate total width: triangle (12px) + gap (2px) + text
    text_width = len(stale_text) * BUILTIN_FONT_WIDTH if stale_text else 0
    indicator_width = 14 + text_width if _wifi_stale_data else 100  # Clear area

    # Clear center area
    clear_x = center_x - indicator_width // 2
    epd.fill_rect(clear_x, y, indicator_width, BUILTIN_FONT_HEIGHT + 2, COLOR_WHITE)

    if not _wifi_stale_data:
        return

    # Position for warning triangle
    tri_x = center_x - indicator_width // 2
    tri_y = y

    # Draw warning triangle outline (11px wide, 6px tall)
    for i in range(6):
        line_width = 1 + i * 2
        line_x = tri_x + 5 - i
        epd.hline(line_x, tri_y + i, line_width, COLOR_BLACK)

    # Exclamation mark inside triangle
    epd.vline(tri_x + 5, tri_y + 1, 2, COLOR_BLACK)
    epd.pixel(tri_x + 5, tri_y + 4, COLOR_BLACK)

    # "STALE Xs" text after triangle
    text_x = tri_x + 14
    epd.text(stale_text, text_x, tri_y, COLOR_BLACK)


def _draw_wifi_status_internal():
    """
    Draw Wi-Fi status indicator in bottom-right corner using cached state.
    Called internally by display update functions.
    """
    global epd, _wifi_connected
    x = DISPLAY_WIDTH - 30
    y = LAST_ROW_TOP_OFFSET

    # Clear the status area first
    epd.fill_rect(x, y, 22, 12, COLOR_WHITE)

    if _wifi_connected:
        # Draw signal bars (3 bars of increasing height)
        for i in range(3):
            bar_height = 4 + i * 3  # Heights: 4, 7, 10
            bar_x = x + i * 6
            bar_y = y + 8 - bar_height
            epd.fill_rect(bar_x, bar_y, 4, bar_height, COLOR_BLACK)
    else:
        # Draw X for disconnected
        epd.text('X', x + 4, y, COLOR_BLACK)


def draw_wifi_status(connected, stale_data=False):
    """
    Update Wi-Fi status state and draw indicator in bottom-right corner.

    Args:
        connected: True if Wi-Fi is connected
        stale_data: True if displaying stale/cached data (stored for stale indicator)
    """
    global _wifi_connected, _wifi_stale_data

    # Store state for redraws
    _wifi_connected = connected
    _wifi_stale_data = stale_data

    # Draw the indicator
    _draw_wifi_status_internal()

    # Partial refresh to show status update
    epd.show_partial()


def _has_arriving_departures(data):
    """Check if there are any departures with countdown == 0."""
    if data is None:
        return False
    for stop in data:
        for line in stop.get('lines', []):
            for dep in line.get('departures', [])[:4]:  # Only check first 4 (displayed)
                if dep.get('countdown', -1) == 0:
                    return True
    return False


def update_arriving_animation():
    """Toggle animation state and redraw display from cached data."""
    global _arriving_indicator_state, _cached_departures

    # Skip animation if no departures are arriving
    if not _has_arriving_departures(_cached_departures):
        print('update_arriving_animation: no arriving departures, skipping')
        return False

    # Toggle the animation state
    old_state = _arriving_indicator_state
    _arriving_indicator_state = not _arriving_indicator_state
    print('update_arriving_animation: toggled {} -> {}'.format(old_state, _arriving_indicator_state))

    # Redraw from cached data if available
    if _cached_departures is not None:
        write_to_display(_cached_departures)
        return True
    print('update_arriving_animation: no cached data, skipping redraw')
    return False


# Track last displayed minute to avoid unnecessary updates
_last_displayed_minute = -1

# Track last data update timestamp
_last_update_time = 0


def update_current_time():
    """Update current time display and stale indicator. Returns True if display was updated."""
    global epd, _last_displayed_minute

    local_time = utime.localtime(utime.time() + get_timezone_offset())
    current_minute = local_time[4]

    # Check if minute changed
    if current_minute == _last_displayed_minute:
        return False

    # Clear the bottom row
    epd.fill_rect(TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, DISPLAY_WIDTH - 2 * TEXT_LEFT_OFFSET, BUILTIN_FONT_HEIGHT + 2, COLOR_WHITE)

    # Draw current time (bottom left)
    current_time_text = '{}:{}'.format(two_digits(local_time[3]), two_digits(local_time[4]))
    epd.text(current_time_text, TEXT_LEFT_OFFSET, LAST_ROW_TOP_OFFSET, COLOR_BLACK)

    # Draw stale indicator (center) if data is stale
    _draw_stale_indicator()

    # Redraw Wi-Fi status (bottom right) - was cleared with the row
    _draw_wifi_status_internal()

    _last_displayed_minute = current_minute

    # Partial refresh for the update
    epd.show_partial()
    return True
