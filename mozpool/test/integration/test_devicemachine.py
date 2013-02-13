# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import mock
from mozpool.lifeguard import devicemachine
from mozpool.test.util import StateDriverMixin, DBMixin, PatchMixin, TestCase

class Tests(StateDriverMixin, DBMixin, PatchMixin, TestCase):

    driver_class = devicemachine.LifeguardDriver

    auto_patch = [
        ('start_ping', 'mozpool.bmm.api.API.start_ping'),
        ('set_pxe', 'mozpool.bmm.api.API.set_pxe'),
        ('start_powercycle', 'mozpool.bmm.api.API.start_powercycle'),
    ]

    def setUp(self):
        super(Tests, self).setUp()
        hw_id = self.add_hardware_type('test', 'test')
        self.add_device('dev1', hardware_type_id=hw_id,
                relayinfo='relayhost:bank1:relay2')

    def tearDown(self):
        super(Tests, self).tearDown()

    def set_state(self, state):
        self.db.devices.set_machine_state('dev1', state, None)

    def assert_state(self, state):
        self.assertEqual(self.db.devices.get_machine_state('dev1'), state)

    def test_free_ping_ok(self):
        self.set_state('free')
        self.driver.handle_timeout('dev1')
        self.start_ping.assert_called_with('dev1', mock.ANY)
        self.start_ping.call_args[0][1](True)
        self.assert_state('free')
