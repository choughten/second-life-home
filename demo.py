"""Synthetic demo data; no personal data and no network access."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs


def response(path):
    now = datetime.now(timezone.utc)
    if path.startswith('/api/art/') or path.startswith('/api/camera/'):
        art = path.startswith('/api/art/')
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"><defs><linearGradient id="g"><stop stop-color="#cb9b91"/><stop offset="1" stop-color="#355568"/></linearGradient></defs><rect width="600" height="400" fill="url(#g)"/><text x="300" y="220" text-anchor="middle" fill="white" font-size="60">%s</text></svg>' % ('♫' if art else 'Demo camera')
        return 200, svg, 'image/svg+xml'
    devices = [
        {'id': 'light.demo_lamp', 'domain': 'light', 'name': 'Reading lamp', 'state': 'on', 'attributes': {}},
        {'id': 'switch.demo_plug', 'domain': 'switch', 'name': 'Desk plug', 'state': 'off', 'attributes': {}},
        {'id': 'climate.demo', 'domain': 'climate', 'name': 'Living room', 'state': 'heat', 'attributes': {'current_temperature': 70, 'temperature': 69, 'current_humidity': 45, 'hvac_action': 'idle', 'hvac_modes': ['heat', 'cool', 'off'], 'min_temp': 50, 'max_temp': 90}},
        {'id': 'camera.demo', 'domain': 'camera', 'name': 'Front garden', 'state': 'idle', 'attributes': {}},
        {'id': 'media_player.demo', 'domain': 'media_player', 'name': 'Living room', 'state': 'playing', 'attributes': {'media_title': 'A second life', 'media_artist': 'Demo artist', 'media_album_name': 'Old hardware, new tricks', 'volume_level': 0.3, 'supported_features': 8320575, 'shuffle': False, 'repeat': 'off', 'group_members': []}},
        {'id': 'media_player.demo_kitchen', 'domain': 'media_player', 'name': 'Kitchen', 'state': 'idle', 'attributes': {'volume_level': 0.2, 'supported_features': 8320575, 'group_members': []}},
    ]
    events = []
    for offset, title in [(0, 'Dinner with friends'), (1, 'Project night'), (2, 'Take a walk'), (3, 'Family call'), (4, 'Game night'), (5, 'Weekend plans')]:
        day = now + timedelta(days=offset)
        events.append({'title': title, 'calendar': 'Demo calendar', 'date': day.strftime('%Y-%m-%d'), 'end': day.strftime('%Y-%m-%d'), 'end_ts': day.timestamp() + 3600, 'sort': day.timestamp(), 'all_day': False, 'time': '6:00 PM', 'day': day.strftime('%a, %b %d')})
    if path == '/api/devices':
        data = {'devices': devices}
    elif path == '/api/status':
        data = {'weather': 'sunny', 'temperature': 68, 'unit': '°F'}
    elif path == '/api/agenda':
        data = {'events': events, 'failed': [], 'updated': 'Demo'}
    elif path.startswith('/api/month?'):
        data = {'events': events, 'failed': [], 'month': parse_qs(urlparse(path).query).get('month', [''])[0]}
    elif path.startswith('/api/music?'):
        category = parse_qs(urlparse(path).query).get('category', ['radio'])[0]
        data = {'items': [{'id': 'demo://%s/%s' % (category, i), 'title': '%s %s' % ('Demo station' if category == 'radio' else 'Demo playlist', i), 'type': 'music'} for i in range(1, 10)]}
    elif path.startswith('/api/music-queue?'):
        data = {'items': [{'label': 'Now', 'title': 'A second life'}, {'label': 'Next', 'title': 'Something new'}], 'count': 2}
    else:
        return 404, {'error': 'Demo endpoint unavailable'}, 'application/json'
    return 200, data, 'application/json'
