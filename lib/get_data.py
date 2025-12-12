import requests

from lib.urlencode import url_encode

REQUEST_URL = 'https://wl-proxy.monsjovis.dev/monitor/next-departures'
FILTER_PARAM_VALUE = '''[
  {
    "diva": "60201438",
    "lines": [
      { "name": "49" },
      { "name": "N49", "direction": "R" },
      { "name": "47A" }
    ]
  },
  {
    "diva": "60200956",
    "lines": [
      { "name": "U4", "direction": "H" }
    ]
  },
  {
    "diva": "60200113",
    "lines": [
      { "name": "52", "direction": "R" }
    ]
  }
]'''.replace('\n', ' ').replace('\r', '').replace('  ', '')

def validate_response(data):
    """Validate API response structure. Returns True if valid."""
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
    url = REQUEST_URL + '?filter=' + url_encode(FILTER_PARAM_VALUE)

    print('Requesting data from:', url)

    response = None
    try:
        response = requests.get(url, headers={'Accept': 'application/json'})
        print('Response code:', response.status_code)
        data = response.json()
        return data
    except Exception as e:
        print('Error during request:', e)
        return None
    finally:
        if response is not None:
            response.close()
