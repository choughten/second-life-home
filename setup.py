"""Interactive setup. Uses only the Python standard library."""
import getpass
import json
import os
import secrets
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def choose(label, items, default_all=True):
    if not items:
        print(label + ': none found (optional).')
        return []
    print('\n' + label)
    for i, item in enumerate(items, 1):
        print('  %s. %s (%s)' % (i, item['attributes'].get('friendly_name', item['entity_id']), item['entity_id']))
    raw = input('Numbers separated by commas, all, or none [all]: ').strip().lower() or 'all'
    if raw == 'all':
        return [x['entity_id'] for x in items]
    if raw == 'none':
        return []
    try:
        indexes = list(dict.fromkeys(int(x.strip()) - 1 for x in raw.split(',')))
        if any(i < 0 or i >= len(items) for i in indexes):
            raise ValueError()
        return [items[i]['entity_id'] for i in indexes]
    except ValueError:
        print('Please enter valid numbers.')
        return choose(label, items)


def main():
    path = Path('config.json')
    if path.exists() and input('Replace existing config.json? [y/N] ').lower() != 'y':
        return
    print('Home Assistant must already be running. Configure your integrations there first.')
    url = input('Home Assistant URL [http://localhost:8123]: ').strip().rstrip('/') or 'http://localhost:8123'
    if urlparse(url).scheme not in ('http', 'https') or not urlparse(url).netloc:
        raise SystemExit('Enter a full HTTP(S) URL.')
    token = os.environ.get('HA_TOKEN') or getpass.getpass('Home Assistant long-lived access token (hidden): ')

    def ha(endpoint):
        req = urllib.request.Request(url + '/api/' + endpoint, headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)

    try:
        states = ha('states')
        info = ha('config')
    except Exception as err:
        raise SystemExit('Could not connect to Home Assistant. Check URL/token and try again (%s).' % type(err).__name__)
    names = {x['entity_id']: x['attributes'].get('friendly_name', x['entity_id']) for x in states}
    by_domain = lambda *domains: [x for x in states if x['entity_id'].split('.')[0] in domains]
    calendars = choose('Calendars', by_domain('calendar'))
    cameras = choose('Cameras', by_domain('camera'))
    music = choose('Music Assistant speakers', [x for x in by_domain('media_player') if x['attributes'].get('app_id') == 'music_assistant'])
    controls = choose('Lights, switches and fans', by_domain('light', 'switch', 'fan'))
    climate = choose('Thermostats', by_domain('climate'))
    sensors = choose('Status sensors', by_domain('sensor', 'binary_sensor'))
    weather = choose('Weather (first selected entity will be used)', by_domain('weather'))
    title = input('Dashboard title [My Home]: ').strip() or 'My Home'
    username = input('Dashboard username [home]: ').strip() or 'home'
    password = getpass.getpass('Dashboard password (blank generates one): ')
    if not password:
        password = secrets.token_urlsafe(18)
        print('Generated dashboard password: ' + password)
    cfg = {
        'title': title, 'location': info.get('location_name', ''),
        'timezone': info.get('time_zone', 'UTC'), 'listen_host': '0.0.0.0', 'port': 8089,
        'ha_url': url, 'ha_token': token, 'auth': {'username': username, 'password': password},
        'calendars': {x: names[x] for x in calendars}, 'cameras': {x: {} for x in cameras},
        'home_camera': cameras[0] if cameras else '', 'music_players': music,
        'weather_entity': weather[0] if weather else '',
        'include_entities': list(dict.fromkeys(cameras + music + controls + climate + sensors)),
        'exclude_entities': [], 'entity_replacements': {}, 'camera_settings': [], 'favorite_buttons': {},
    }
    # An empty selection must not silently mean every device is authorized.
    if not cfg['include_entities']:
        cfg['include_entities'] = ['__none__']
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(cfg, f, indent=2)
    print('\nSaved private config.json. Run: python3 server.py')
    print('Open http://<this-computer-LAN-address>:8089 on the tablet and sign in.')


if __name__ == '__main__':
    main()
