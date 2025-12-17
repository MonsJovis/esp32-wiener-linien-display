import requests
from gc import collect
from lib.config import get_stops

# Wiener Linien Open Government Data API
API_BASE_URL = 'https://www.wienerlinien.at/ogd_realtime/monitor'


def get_diva_ids():
    """Get list of DIVA IDs from configuration."""
    return [stop['diva'] for stop in get_stops()]


def get_line_filters():
    """Get line filters from configuration as {diva: {line_name: [directions]}}."""
    return {stop['diva']: stop['lines'] for stop in get_stops()}


def build_api_url():
    """Build the Wiener Linien API URL with diva parameters."""
    diva_ids = get_diva_ids()
    params = '&'.join('diva=' + diva for diva in diva_ids)
    return API_BASE_URL + '?' + params


def parse_server_time(server_time):
    """
    Convert serverTime to localeTimestamp format.

    Input: "2025-12-16T10:25:00.000+0100"
    Output: "2025-12-16 10:25:00"
    """
    if not server_time:
        return ''

    try:
        # Split at 'T' to get date and time parts
        parts = server_time.split('T')
        if len(parts) != 2:
            return ''

        date_part = parts[0]
        time_part = parts[1]

        # Extract time (remove milliseconds and timezone)
        # Format: "10:25:00.000+0100" -> "10:25:00"
        time_clean = time_part.split('.')[0]

        return date_part + ' ' + time_clean
    except Exception as e:
        print('Error parsing server_time:', e)
        return ''


def transform_response(api_response):
    """
    Transform Wiener Linien API response to simplified format.

    Input structure:
    {
        "data": {
            "monitors": [{
                "locationStop": {"properties": {"name": "60201438", "title": "Stop Name"}},
                "lines": [{
                    "name": "49",
                    "towards": "DESTINATION",
                    "direction": "R",
                    "departures": {
                        "departure": [{
                            "departureTime": {"countdown": 5},
                            "vehicle": {"barrierFree": true, "realtimeSupported": true}
                        }]
                    }
                }]
            }]
        },
        "message": {"serverTime": "2025-12-16T10:25:00.000+0100"}
    }

    Output structure (matching proxy format):
    {
        "data": [{
            "name": "Stop Name",
            "diva": "60201438",
            "lines": [{
                "name": "49",
                "direction": "R",
                "towards": "DESTINATION",
                "departures": [{"countdown": 5}]
            }]
        }],
        "localeTimestamp": "2025-12-16 10:25:00"
    }
    """
    # Use dict to merge stops with same DIVA ID
    stops_by_diva = {}

    monitors = api_response.get('data', {}).get('monitors', [])
    line_filters = get_line_filters()

    for monitor in monitors:
        # Extract stop info
        props = monitor.get('locationStop', {}).get('properties', {})
        diva = props.get('name', '')
        stop_name = props.get('title', '')

        # Skip if this DIVA is not in our filter
        if diva not in line_filters:
            continue

        allowed_lines = line_filters[diva]

        for line in monitor.get('lines', []):
            line_name = line.get('name', '')
            line_direction = line.get('direction', '')

            # Check if line passes filter
            if line_name not in allowed_lines:
                continue

            allowed_directions = allowed_lines[line_name]
            if allowed_directions and line_direction not in allowed_directions:
                continue

            # Extract departures
            departures_data = line.get('departures', {}).get('departure', [])
            departures = []

            for dep in departures_data:
                dep_time = dep.get('departureTime', {})
                departures.append({
                    'countdown': dep_time.get('countdown', 0),
                })

            if departures:
                # Create stop entry if needed
                if diva not in stops_by_diva:
                    stops_by_diva[diva] = {
                        'name': stop_name,
                        'diva': diva,
                        'lines': [],
                    }

                stops_by_diva[diva]['lines'].append({
                    'name': line_name,
                    'direction': line_direction,
                    'towards': line.get('towards', ''),
                    'departures': departures,
                })

    result_data = list(stops_by_diva.values())

    # Generate timestamp from serverTime
    server_time = api_response.get('message', {}).get('serverTime', '')
    locale_timestamp = parse_server_time(server_time)

    return {
        'data': result_data,
        'localeTimestamp': locale_timestamp,
    }


def validate_response(data):
    """Validate transformed response structure. Returns True if valid."""
    if not isinstance(data, dict):
        return False
    if 'data' not in data or not isinstance(data['data'], list):
        return False
    if 'localeTimestamp' not in data:
        return False
    # Validate each stop has expected structure
    for stop in data['data']:
        if not isinstance(stop, dict) or 'lines' not in stop:
            return False
        for line in stop['lines']:
            if not isinstance(line, dict) or 'name' not in line or 'departures' not in line:
                return False
    return True


def get_data():
    data = make_request()
    if data is None:
        return None

    # Validate response structure before processing
    if not validate_response(data):
        print('Error: Invalid API response structure')
        return None

    print('--- Start Output ---\n')

    # Iterate through the data to extract and print departure times and countdowns
    for stop in data['data']:
        for line in stop['lines']:
            line_name = line['name']
            countdowns = [str(departure.get('countdown', '?')) for departure in line['departures']]
            print('{}: {}'.format(line_name, ', '.join(countdowns)))

    print('\n--- End Output ---\n')

    return data


def make_request():
    """Fetch data from Wiener Linien API and transform it."""
    import ujson

    url = build_api_url()

    print('make_request: requesting from:', url)

    # Force GC multiple times before request to maximize available memory
    # This helps defragment memory for the TLS handshake which needs large contiguous blocks
    print('make_request: running gc.collect() before request')
    collect()
    collect()
    collect()

    # Log available memory for debugging
    import gc as gc_module
    print('make_request: free memory:', gc_module.mem_free(), 'bytes')

    response = None
    try:
        print('make_request: starting HTTP GET (timeout=5s)...')
        response = requests.get(url, headers={'Accept': 'application/json'}, timeout=5)
        print('make_request: HTTP GET complete, status:', response.status_code)

        if response.status_code != 200:
            print('make_request: Error - non-200 response, closing')
            response.close()
            return None

        # Stream JSON parsing - read directly from socket
        # ujson.load() reads from file-like object
        print('make_request: parsing JSON response...')
        raw_data = ujson.load(response.raw)
        print('make_request: JSON parsed successfully')

        # Close response immediately after parsing
        print('make_request: closing response')
        response.close()
        response = None
        collect()

        # Transform to simplified format
        print('make_request: transforming response...')
        result = transform_response(raw_data)
        print('make_request: transformation complete')

        # Force garbage collection after transformation
        collect()

        return result

    except Exception as e:
        print('make_request: Error -', type(e).__name__, e)
        import sys
        sys.print_exception(e)
        return None
    finally:
        if response is not None:
            print('make_request: closing response in finally block')
            response.close()
