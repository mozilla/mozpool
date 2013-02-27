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
        ('ping', 'mozpool.bmm.api.API.ping'),
        ('set_pxe', 'mozpool.bmm.api.API.set_pxe'),
        ('powercycle', 'mozpool.bmm.api.API.powercycle'),
        ('requests_post', 'mozpool.async.AsyncRequests.post'),
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

    def invoke_callback(self, start_mock, result):
        "call the callback passed to a mock async operation start"
        start_mock.assert_called()
        start_mock.call_args[0][0](result)

    def requests_result(self, mock, status_code):
        r = mock.Mock()
        r.status_code = status_code
        self.invoke_callback(mock.start, r)

    def test_free_ping_ok(self):
        self.set_state('free')
        self.driver.handle_timeout('dev1')
        self.ping.start.assert_called_with(mock.ANY, 'dev1')
        self.invoke_callback(self.ping.start, True)
        self.assert_state('free')

    def test_free_ping_selftest(self):
        # add a self-test image and pxe_config for this device and hardware type
        self.add_image('self-test')
        self.add_pxe_config('selftest', contents='SELF TEST')
        self.add_image_pxe_config('self-test', 'selftest', 'test', 'test')

        self.set_state('free')
        self.driver.handle_timeout('dev1')
        self.ping.start.assert_called_with(mock.ANY, 'dev1')
        self.invoke_callback(self.ping.start, False) # ping fails
        self.set_pxe.run.assert_called_with('dev1', 'selftest')
        self.powercycle.start.assert_called_with(mock.ANY, 'dev1')
        self.assert_state('pxe_power_cycling')

    def test_ready_no_next_image(self):
        "entering ready does not change the image if there's no next_image"
        self.add_image('old_img')
        self.db.devices.set_image('dev1', 'old_img', '{bc}')
        self.set_state('sut_sdcard_verifying')
        self.driver.handle_event('dev1', 'sut_sdcard_ok', {})
        self.assert_state('ready')
        self.assertEqual(self.db.devices.get_image('dev1'),
                {'image': 'old_img', 'boot_config': '{bc}'})

    def test_ready_set_image(self):
        "entering ready changes the image if there is a next_image"
        self.add_image('old_img')
        self.add_image('new_img')
        self.db.devices.set_image('dev1', 'old_img', '{bc}')
        self.db.devices.set_next_image('dev1', 'new_img', '{bc2}')
        self.set_state('sut_sdcard_verifying')
        self.driver.handle_event('dev1', 'sut_sdcard_ok', {})
        self.assert_state('ready')
        self.assertEqual(self.db.devices.get_image('dev1'),
                {'image': 'new_img', 'boot_config': '{bc2}'})

    def test_ready_no_request(self):
        "entering the ready state doesn't notify mozpool if there's no request"
        self.set_state('sut_sdcard_verifying')
        self.driver.handle_event('dev1', 'sut_sdcard_ok', {})
        self.requests_post.start.assert_not_called()
        self.assert_state('ready')

    def test_ready_notifies_mozpool(self):
        "entering the ready state notifies mozpool if there's an attached request"
        self.add_image('img1')
        req_id = self.add_request(device='dev1', image='img1')

        self.set_state('sut_sdcard_verifying')
        self.driver.handle_event('dev1', 'sut_sdcard_ok', {})
        self.requests_post.start.assert_called_with(mock.ANY,
                'http://server/api/request/%d/event/lifeguard_finished/' % req_id,
                data='{"imaging_result": "complete"}')
        self.assert_state('ready')
        self.requests_result(self.requests_post, 500) # just to test the logging

    def test_failed_b2g_downloading_notifies_mozpool(self):
        """
        failed_b2g_downloading (and by extension other failed_* states notify
        mozpool if there's an attached request
        """
        self.add_image('img1')
        req_id = self.add_request(device='dev1', image='img1')

        self.set_state('b2g_downloading')
        self.db.devices.set_counters('dev1', {"b2g_downloading": 10000})
        self.driver.handle_timeout('dev1')
        self.requests_post.start.assert_called_with(mock.ANY,
                'http://server/api/request/%d/event/lifeguard_finished/' % req_id,
                data='{"imaging_result": "failed-bad-device"}')
        self.assert_state('failed_b2g_downloading')
        self.requests_result(self.requests_post, 200)
