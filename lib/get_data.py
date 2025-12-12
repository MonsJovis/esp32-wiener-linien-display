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

def get_data():
    data = make_request()
    if (data is None):
        return

    print('--- Start Output ---\n')

    # Iterate through the data to extract and print departure times and countdowns
    for stop in data['data']:
        for line in stop['lines']:
            line_name = line['name']
            countdowns = [f"{departure['countdown']}" for departure in line['departures']]
            print(f"{line_name}: {'\", '.join(countdowns)}\"")

    print('\n--- End Output ---\n')

    return data

def make_request():
    global REQUEST_URL, FILTER_PARAM_VALUE
    url = REQUEST_URL + '?filter=' + url_encode(FILTER_PARAM_VALUE)

    print('Requesting data from:', url)

    try:
        # Make the request
        response = requests.get(url, headers={'Accept': 'application/json'})
        #Print the response code
        print('Response code: ', response.status_code)

    except Exception as e:
        # Handle any exceptions during the request
        print('Error during request:', e)
        response.close()

        return None

    try:
        data = response.json()
    except Exception as e:
        data = None
        print('Error parsing JSON response')

    finally:
        response.close()

    return data
