# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
from mozpool.bmm import relay
from mozpool.test import fakerelay
from mozpool.test.util import TestCase

class Tests(TestCase):

    # NOTE: this class assumes "real-time" timing down to a 100th of a second.
    # The advantage is that it really tests socket timeouts, rather than faking
    # them out.

    def setUp(self):
        # start up a fake relay server, and set relay.PORT to point to it
        self.relayboard = fakerelay.RelayBoard('test', ('127.0.0.1', 0), record_actions=True)
        self.relayboard.add_relay(2, 2, fakerelay.Relay())
        thd = self.relayboard.spawn_one()
        self.addCleanup(thd.join)
        self.relay_host = '127.0.0.1:%d' % self.relayboard.get_port()

        relay.ONE_SECOND = 0.05

    def tearDown(self):
        relay.ONE_SECOND = 1

    @mock.patch('time.sleep')
    def test_get_status(self, sleep):
        self.assertEqual(relay.get_status(self.relay_host, 2, 2, 10), True)
        self.assertEqual(self.relayboard.actions, [('get', 2, 2)])

    def test_get_status_timeout(self):
        self.relayboard.delay = 0.12
        self.relayboard.skip_final_1s = True
        self.assertEqual(relay.get_status(self.relay_host, 2, 2, 0.1), None)

    @mock.patch('time.sleep')
    def test_set_status_on(self, sleep):
        self.assertEqual(relay.set_status(self.relay_host, 2, 2, True, 10), True)
        self.assertEqual(self.relayboard.actions, [('set', 'panda-on', 2, 2)])

    @mock.patch('time.sleep')
    def test_set_status_off(self, sleep):
        self.assertEqual(relay.set_status(self.relay_host, 2, 2, False, 10), True)
        self.assertEqual(self.relayboard.actions, [('set', 'panda-off', 2, 2)])

    def test_set_status_timeout(self):
        self.relayboard.delay = 0.12
        self.relayboard.skip_final_1s = True
        self.assertEqual(relay.set_status(self.relay_host, 2, 2, True, 0.1), False)

    @mock.patch('time.sleep')
    def test_powercycle(self, sleep):
        self.assertEqual(relay.powercycle(self.relay_host, 2, 2, 10), True)
        self.assertEqual(self.relayboard.actions,
                [('set', 'panda-off', 2, 2), ('get', 2, 2), ('set', 'panda-on', 2, 2), ('get', 2, 2)])

    def test_powercycle_timeout(self):
        self.relayboard.delay = 0.06
        self.relayboard.skip_final_1s = True
        self.assertEqual(relay.powercycle(self.relay_host, 2, 2, 0.1), False)

    @mock.patch('time.sleep')
    def test_test_two_way_comms(self, sleep):
        self.assertEqual(relay.test_two_way_comms(self.relay_host, 10), True)

    def test_test_two_way_comms_timeout(self):
        self.relayboard.delay = 0.12
        self.relayboard.skip_final_1s = True
        self.assertEqual(relay.test_two_way_comms(self.relay_host, 0.1), False)
