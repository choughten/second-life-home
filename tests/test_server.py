import base64
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.cfg = {
            'ha_token': 'test-only-token', 'auth': {'username': 'test', 'password': 'test-only-password'},
            'title': '</script><script>bad()</script>', 'timezone': 'UTC',
            'include_entities': ['light.test', 'climate.test', 'media_player.test', 'media_player.second'],
            'music_players': ['media_player.test', 'media_player.second'],
        }
        path = Path(cls.temp.name) / 'config.json'
        path.write_text(json.dumps(cls.cfg))
        with patch.dict(os.environ, {'DASHBOARD_CONFIG': str(path), 'DASHBOARD_DEMO': '0', 'HA_TOKEN': '', 'DASHBOARD_USERNAME': '', 'DASHBOARD_PASSWORD': ''}):
            spec = importlib.util.spec_from_file_location('tested_server', ROOT / 'server.py')
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
        cls.http = cls.module.ThreadingHTTPServer(('127.0.0.1', 0), cls.module.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%s' % cls.http.server_port
        cls.auth = 'Basic ' + base64.b64encode(b'test:test-only-password').decode()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.temp.cleanup()

    def setUp(self):
        self.calls = []
        self.states = [
            {'entity_id': 'light.test', 'state': 'off', 'attributes': {'friendly_name': 'Test lamp', 'access_token': 'never-export-this'}},
            {'entity_id': 'light.private', 'state': 'on', 'attributes': {}},
            {'entity_id': 'climate.test', 'state': 'heat', 'attributes': {'min_temp': 50, 'max_temp': 90, 'temperature': 69, 'hvac_modes': ['heat', 'off'], 'preset_modes': ['none', 'eco']}},
            {'entity_id': 'media_player.test', 'state': 'playing', 'attributes': {'group_members': ['media_player.test', 'media_player.second']}},
            {'entity_id': 'media_player.second', 'state': 'idle', 'attributes': {}},
        ]

        def ha(path, data=None):
            if data is not None:
                self.calls.append((path, data))
                return {}
            if path == 'states':
                return self.states
            if path.startswith('states/'):
                return next(x for x in self.states if x['entity_id'] == path[7:])
            raise AssertionError(path)

        self.mock = patch.object(self.module, 'ha', side_effect=ha)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def request(self, path='/', payload=None, auth=True, origin=None):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = self.auth
        if payload is not None:
            headers['X-Dashboard'] = 'ipad'
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.base + path, headers=headers, data=None if payload is None else json.dumps(payload).encode())
        try:
            result = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as err:
            result = err
        with result:
            return result.status, result.read()

    def test_every_endpoint_requires_authentication(self):
        for path in ['/', '/health', '/api/devices', '/api/art/media_player.test', '/api/camera/camera.test']:
            self.assertEqual(self.request(path, auth=False)[0], 401)
        self.assertFalse(self.calls)

    def test_public_config_is_escaped_and_has_no_credentials(self):
        status, body = self.request()
        self.assertEqual(status, 200)
        self.assertIn(b'\\u003c/script>', body)
        self.assertNotIn(b'test-only-token', body)
        self.assertNotIn(b'test-only-password', body)

    def test_devices_are_allowlisted_and_secrets_removed(self):
        _, body = self.request('/api/devices')
        data = json.loads(body)
        self.assertEqual(len(data['devices']), 4)
        self.assertNotIn(b'never-export-this', body)
        self.assertNotIn(b'light.private', body)

    def test_commands_route_to_expected_service(self):
        status, _ = self.request('/api/control', {'entity': 'light.test', 'action': 'turn_on'}, origin=self.base)
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, [('services/light/turn_on', {'entity_id': 'light.test'})])

    def test_bad_origin_does_not_control_devices(self):
        self.assertEqual(self.request('/api/control', {'entity': 'light.test', 'action': 'turn_on'}, origin='https://other.example')[0], 403)
        self.assertFalse(self.calls)

    def test_invalid_commands_never_call_services(self):
        for command in [
            {'entity': 'light.private', 'action': 'turn_on'},
            {'entity': 'light.test', 'action': 'delete_everything'},
            {'entity': 'media_player.test', 'action': 'volume_set', 'volume_level': 9},
            {'entity': 'climate.test', 'action': 'set_temperature', 'temperature': 999},
            {'entity': 'media_player.test', 'action': 'set_speakers', 'members': ['media_player.test', 'media_player.stranger']},
        ]:
            self.assertIn(self.request('/api/control', command)[0], (400, 403, 404))
        self.assertFalse(self.calls)

    def test_group_selection_keeps_existing_main(self):
        status, _ = self.request('/api/control', {'entity': 'media_player.test', 'action': 'set_speakers', 'members': ['media_player.test', 'media_player.second']})
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, [('services/media_player/join', {'entity_id': 'media_player.test', 'group_members': ['media_player.second']})])

    def test_removed_speaker_is_unjoined(self):
        status, _ = self.request('/api/control', {'entity': 'media_player.test', 'action': 'set_speakers', 'members': ['media_player.test']})
        self.assertEqual(status, 200)
        self.assertIn(('services/media_player/unjoin', {'entity_id': 'media_player.second'}), self.calls)

    def test_demo_cannot_send_commands(self):
        with patch.object(self.module, 'DEMO', True):
            self.assertEqual(self.request('/api/control', {'entity': 'light.test', 'action': 'turn_on'})[0], 409)
        self.assertFalse(self.calls)

    def test_unknown_media_cannot_be_played(self):
        with patch.object(self.module, 'music_items', return_value=[{'id': 'library://radio/1', 'title': 'Allowed', 'type': 'music'}]):
            status, _ = self.request('/api/control', {'entity': 'media_player.test', 'action': 'play_selection', 'category': 'radio', 'item': 'https://attacker.example/audio'})
        self.assertEqual(status, 400)
        self.assertFalse(self.calls)

    def test_auto_and_eco_target_changes_are_rejected(self):
        climate = self.states[2]
        for state, preset in [('heat_cool', 'none'), ('heat', 'eco'), ('off', 'none')]:
            climate['state'] = state
            climate['attributes']['preset_mode'] = preset
            self.assertEqual(self.request('/api/control', {'entity': 'climate.test', 'action': 'set_temperature', 'temperature': 70})[0], 409)
        self.assertFalse(self.calls)


class WizardTests(unittest.TestCase):
    def test_wizard_discovers_selected_entities_and_writes_private_config(self):
        spec = importlib.util.spec_from_file_location('setup_wizard', ROOT / 'setup.py')
        wizard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wizard)
        states = [{'entity_id': domain + '.sample', 'attributes': {'friendly_name': domain, 'app_id': 'music_assistant'}} for domain in ['calendar', 'camera', 'media_player', 'light', 'climate', 'sensor', 'weather']]

        def fake_open(req, timeout):
            return io.BytesIO(json.dumps({'time_zone': 'UTC'} if req.full_url.endswith('/api/config') else states).encode())

        answers = iter(['http://ha.example:8123'] + ['all'] * 7 + ['Test home', 'test'])
        old_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                with patch('builtins.input', side_effect=lambda _: next(answers)), patch.object(wizard.getpass, 'getpass', side_effect=['fake-token', 'fake-password']), patch.dict(os.environ, {'HA_TOKEN': ''}), patch.object(wizard.urllib.request, 'urlopen', side_effect=fake_open), patch('sys.stdout', new_callable=io.StringIO):
                    wizard.main()
                config = json.loads(Path('config.json').read_text())
                self.assertEqual(config['music_players'], ['media_player.sample'])
                self.assertEqual(config['calendars'], {'calendar.sample': 'calendar'})
                self.assertEqual(config['include_entities'], ['camera.sample', 'media_player.sample', 'light.sample', 'climate.sample', 'sensor.sample'])
                if os.name != 'nt':
                    self.assertEqual(Path('config.json').stat().st_mode & 0o777, 0o600)
        finally:
            os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
