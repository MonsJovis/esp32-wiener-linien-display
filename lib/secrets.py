import ujson

secrets = None

def load_secrets():
    try:
        with open('secrets.json') as fp:
            return ujson.loads(fp.read())
    except (OSError, ValueError) as e:
        print('Error loading secrets:', e)
        return {}

def get_wifi_secrets():
    global secrets

    if secrets is None:
        secrets = load_secrets()

    try:
        return secrets['wifi']['ssid'], secrets['wifi']['password']
    except (KeyError, TypeError) as e:
        print('Error: secrets.json missing wifi.ssid or wifi.password')
        raise ValueError('Invalid secrets.json format. Expected: {"wifi": {"ssid": "...", "password": "..."}}')
