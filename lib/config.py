"""
Configuration loader module.
Loads settings from config.json for runtime configuration without code changes.
"""

import ujson

_config = None


def load_config():
    """Load and cache configuration from config.json."""
    global _config
    if _config is None:
        try:
            with open('config.json', 'r') as f:
                _config = ujson.load(f)
        except OSError as err:
            raise RuntimeError('config.json not found. Please create it from config.json.example') from err
    return _config


def get_stops():
    """Get list of stops with their line filters."""
    return load_config()['stops']


def get_line_priority():
    """Get line priority order for display sorting."""
    return load_config()['line_priority']


def get_update_interval():
    """Get data refresh interval in seconds."""
    return load_config()['update_interval_sec']


def get_animation_interval():
    """Get animation toggle interval in seconds."""
    return load_config()['animation_interval_sec']


def get_full_refresh_interval():
    """Get number of updates between full e-paper refreshes."""
    return load_config()['full_refresh_interval_cycles']


def get_wlan_config():
    """Get Wi-Fi configuration (timeout_sec, reconnect_delay_sec, max_retries)."""
    return load_config()['wlan']


def get_watchdog_timeout():
    """Get watchdog timeout in milliseconds."""
    return load_config()['watchdog_timeout_ms']


def get_stale_restart_threshold():
    """Get stale data restart threshold in seconds."""
    return load_config()['stale_restart_threshold_sec']


def get_destination_shortnames():
    """Get destination name abbreviations mapping."""
    return load_config().get('destination_shortnames', {})
