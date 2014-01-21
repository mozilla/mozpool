# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import datetime
import mozpool.mozpool
from mozpool import config
from mozpool.test.util import TestCase, AppMixin, DBMixin, ConfigMixin

class Tests(AppMixin, DBMixin, ConfigMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        config.set('server', 'fqdn', 'server')
        self.add_server('server')
        self.add_image('img1', boot_config_keys='[]')
        self.add_image('img2', boot_config_keys='["aa", "bb"]')
        self.dev_id = self.add_device('dev1', environment='abc')

        mozpool.lifeguard.driver = mock.Mock()

    def test_state_change(self):
        mozpool.lifeguard.driver.conditional_state_change.return_value = True
        self.check_json_result(self.app.post('/api/device/dev1/state-change/blue/to/green/'))
        mozpool.lifeguard.driver.conditional_state_change.assert_called_with('dev1', 'blue', 'green')

    def test_state_change_conflict(self):
        mozpool.lifeguard.driver.conditional_state_change.return_value = False
        r = self.app.post('/api/device/dev1/state-change/blue/to/green/', expect_errors=True)
        self.assertEqual(r.status, 409)

    def test_event_GET(self):
        self.check_json_result(self.app.get('/api/device/dev1/event/shorted/'))
        mozpool.lifeguard.driver.handle_event.assert_called_with('dev1', 'shorted', {})

    def test_event_POST(self):
        self.check_json_result(self.post_json('/api/device/dev1/event/shorted/', {'a': 'b'}))
        mozpool.lifeguard.driver.handle_event.assert_called_with('dev1', 'shorted', {'a': 'b'})

    def test_status(self):
        self.add_device_log(self.dev_id, 'hello', 'tests', datetime.datetime(1978, 6, 15))
        body = self.check_json_result(self.app.get('/api/device/dev1/status/'))
        self.assertEqual(body, {
            'log': [
                {'id': 1, 'message': 'hello', 'source': 'tests', 'timestamp': '1978-06-15T00:00:00'},
            ],
            'state': 'offline'})

    def test_state(self):
        body = self.check_json_result(self.app.get('/api/device/dev1/state/'))
        self.assertEqual(body, { 'state': 'offline' })

    def test_state_cached(self):
        # note that the caching itself is tested elsewhere
        body = self.check_json_result(self.app.get('/api/device/dev1/state/?cache=1'))
        self.assertEqual(body, { 'state': 'offline' })
