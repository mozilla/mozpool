# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

from mozpool.mozpool import requestmachine
from mozpool.test.util import StateDriverMixin, DBMixin, PatchMixin, TestCase

class Tests(StateDriverMixin, DBMixin, PatchMixin, TestCase):

    driver_class = requestmachine.MozpoolDriver

    auto_patch = [
        ('urlopen', 'urllib.urlopen')
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

    def test_new(self):
        self.set_state('new')
        self.driver.handle_event(self.req_id, 'find_device', {})
        # the finding_device state assigns a device..
        dev = self.db.requests.get_assigned_device(self.req_id)
        self.assertEqual(dev, 'dev1')
        # the contacting_lifeguard state contacts lifeguard..
        self.urlopen.assert_called_with('http://server/api/device/dev1/event/please_image/',
                                        '{"image": "img1", "boot_config": "{}"}')
        # and then the machine ends up in the pending state
        self.assert_state('pending')
