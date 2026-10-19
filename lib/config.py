"""
Configuration loader module.
Loads settings from config.json for runtime configuration without code changes.

config.json belongs to the device: only a USB deploy writes it, an OTA update
never does (lib/ota_policy.path_allowed). It holds what is the device's own
(stops, line_priority, destination_shortnames) and overrides any of the
DEFAULTS below, which ship with the app, so an update can add or change a
setting without touching a device's config.
"""

import ujson

DEFAULTS = {
    'update_interval_sec': 45,  # lower runs into the API rate limit
    'animation_interval_sec': 1,
    'full_refresh_interval_cycles': 600,
    'wlan': {'timeout_sec': 60, 'reconnect_delay_sec': 5, 'max_retries': 10},
    'stale_restart_threshold_sec': 300,
    'watchdog_timeout_ms': 90000,
    'ota': {
        # An empty string in a device's config.json turns updates off.
        'manifest_url': 'https://github.com/MonsJovis/esp32-wiener-linien-display/releases/latest/download/manifest.json',
        'install_hours': [3, 5],
    },
}

_config = None


def _merge(defaults, own):
    """own over defaults; nested objects (wlan, ota) key by key."""
    merged = dict(defaults)
    for key, value in own.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            value = _merge(merged[key], value)
        merged[key] = value
    return merged


def load_config():
    """Load and cache configuration from config.json, over DEFAULTS."""
    global _config
    if _config is None:
        try:
            with open('config.json', 'r') as f:
                _config = _merge(DEFAULTS, ujson.load(f))
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


def get_ota_config():
    """Get OTA update settings (manifest_url, install_hours). Empty manifest_url = updates off."""
    return load_config()['ota']
