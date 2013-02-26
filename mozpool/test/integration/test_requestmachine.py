# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
from mozpool.mozpool import requestmachine
from mozpool.test.util import StateDriverMixin, DBMixin, PatchMixin, TestCase

class Tests(StateDriverMixin, DBMixin, PatchMixin, TestCase):

    driver_class = requestmachine.MozpoolDriver

    auto_patch = [
        ('requests_get', 'mozpool.async.AsyncRequests.get'),
        ('requests_post', 'mozpool.async.AsyncRequests.post'),
    ]

    def setUp(self):
        super(Tests, self).setUp()
        self.add_image('img1', can_reuse=False)
        self.req_id = self.add_request(image='img1', no_assign=True)
        self.add_device('dev1', state='free')

    def tearDown(self):
        super(Tests, self).tearDown()

    def set_state(self, state):
        self.db.requests.set_machine_state(self.req_id, state, None)

    def assert_state(self, state):
        self.assertEqual(self.db.requests.get_machine_state(self.req_id), state)

    def invoke_callback(self, start_mock, result):
        "call the callback passed to a mock async operation start"
        start_mock.assert_called()
        start_mock.call_args[0][0](result)

    def requests_result(self, mock, status_code):
        r = mock.Mock()
        r.status_code = status_code
        self.invoke_callback(mock.start, r)

    def test_new(self):
        self.set_state('new')
        self.driver.handle_event(self.req_id, 'find_device', {})
        # the finding_device state assigns a device..
        dev = self.db.requests.get_assigned_device(self.req_id)
        self.assertEqual(dev, 'dev1')
        # the contacting_lifeguard state contacts lifeguard..
        self.requests_post.start.assert_called_with(mock.ANY,
                'http://server/api/device/dev1/event/please_image/',
                data='{"image": "img1", "boot_config": "{}"}')
        self.requests_result(self.requests_post, 200)
        # and then the machine ends up in the pending state
        self.assert_state('pending')

    def test_new_lifeguard_fails(self):
        self.set_state('new')
        self.driver.handle_event(self.req_id, 'find_device', {})
        # the finding_device state assigns a device..
        dev = self.db.requests.get_assigned_device(self.req_id)
        self.assertEqual(dev, 'dev1')
        # the contacting_lifeguard state contacts lifeguard, failing repeatedly
        for _ in range(5):
            self.requests_post.start.assert_called_with(mock.ANY,
                    'http://server/api/device/dev1/event/please_image/',
                    data='{"image": "img1", "boot_config": "{}"}')
            self.reset_all_mocks()
            self.driver.handle_timeout(self.req_id)
        # and finally the machine ends up in the device_not_found state
        self.assert_state('device_not_found')

    def test_closing(self):
        self.set_state('ready')
        self.add_device_request(self.req_id, 'dev1')
        self.driver.handle_event(self.req_id, 'close', {})
        self.assert_state('closing')
        self.requests_get.start.assert_called_with(mock.ANY,
                'http://server/api/device/dev1/event/free/')
        self.requests_result(self.requests_get, 200)
        self.assert_state('closed')

    def test_closing_lifeguard_fails(self):
        self.set_state('ready')
        self.add_device_request(self.req_id, 'dev1')
        self.driver.handle_event(self.req_id, 'close', {})
        self.assert_state('closing')
        for _ in range(10):
            self.requests_get.start.assert_called_with(mock.ANY,
                    'http://server/api/device/dev1/event/free/')
            self.reset_all_mocks()
            self.driver.handle_timeout(self.req_id)
        self.assert_state('closed')
