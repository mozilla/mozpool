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
        self.add_device('dev1', state='ready')

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
        # the contact(ing)_lifeguard states contact lifeguard..
        self.assert_state('contact_lifeguard')
        self.driver.handle_timeout(self.req_id)
        self.assert_state('contacting_lifeguard')
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
        self.assert_state('contact_lifeguard')
        self.driver.handle_timeout(self.req_id)
        self.assert_state('contacting_lifeguard')
        # the contacting_lifeguard state contacts lifeguard, failing repeatedly
        for _ in range(5):
            self.requests_post.start.assert_called_with(mock.ANY,
                    'http://server/api/device/dev1/event/please_image/',
                    data='{"image": "img1", "boot_config": "{}"}')
            self.reset_all_mocks()
            self.driver.handle_timeout(self.req_id)
        # and finally the machine ends up in the failed_device_not_found state
        self.assert_state('failed_device_not_found')

    def test_new_lifeguard_fails_bad_device(self):
        self.req_id = self.add_request(image='img1', device='dev1')
        self.db.devices.set_machine_state('dev1', 'failed_dead', None)
        self.set_state('new')
        self.driver.handle_event(self.req_id, 'find_device', {})
        self.assert_state('failed_bad_device')

    def test_pending_result_complete(self):
        self.set_state('pending')
        self.add_device_request(self.req_id, 'dev1')
        self.driver.handle_event(self.req_id, 'lifeguard_finished',
                {'imaging_result': 'complete'})
        self.assert_state('ready')

    def test_pending_result_complete_timeout(self):
        self.set_state('pending')
        self.add_device_request(self.req_id, 'dev1')
        self.db.device_requests.set_result('dev1', 'complete')
        self.driver.handle_timeout(self.req_id)
        self.assert_state('ready')

    def test_pending_result_bad_image(self):
        self.set_state('new')
        num_tries = 2

        # add enough devices to satisfy the retries
        for i in range(2, num_tries+1):
            self.add_device('dev%d' % i, state='ready')

        # retry NUM_RETRIES times
        self.driver.handle_event(self.req_id, 'find_device', {})
        for _ in range(num_tries):
            assigned_dev = self.db.requests.get_assigned_device(self.req_id)
            self.assert_state('contact_lifeguard')
            self.driver.handle_timeout(self.req_id)
            self.assert_state('contacting_lifeguard')
            self.db.devices.set_machine_state(assigned_dev, 'busy', None)
            self.requests_result(self.requests_post, 200)
            self.assert_state('pending')
            self.driver.handle_event(self.req_id, 'lifeguard_finished',
                    {'imaging_result': 'failed-bad-image'})

        # finally it fails..
        self.assert_state('failed_bad_image')

    def test_pending_result_bad_device(self):
        self.set_state('pending')
        self.add_device_request(self.req_id, 'dev1')
        self.db.devices.set_machine_state('dev1', 'busy', None)
        self.add_device('dev2', state='ready')

        self.driver.handle_event(self.req_id, 'lifeguard_finished',
                {'imaging_result': 'failed-bad-device'})

        # device is released and we're back to looking for a device and contacting
        # lifeguard.  This is contacting lifegaurd about dev2, since it's ready.
        self.assert_state('contact_lifeguard')
        self.assertEqual(self.db.device_requests.get_by_device('dev1'), None)
        self.assertEqual(self.db.device_requests.get_by_device('dev2'), self.req_id)

    def test_pending_result_bad_device_single_device(self):
        self.req_id = self.add_request(image='img1', device='dev1')
        self.set_state('pending')
        self.db.devices.set_machine_state('dev1', 'failed_dead', None)

        self.driver.handle_event(self.req_id, 'lifeguard_finished',
                {'imaging_result': 'failed-bad-device'})

        self.assert_state('failed_bad_device')
        self.assertEqual(self.db.device_requests.get_by_device('dev1'), None)

    def test_pending_result_timeout_failed(self):
        # in this case, the request is for 'any', so it times out
        self.set_state('pending')
        self.add_device_request(self.req_id, 'dev1')
        self.db.devices.set_machine_state('dev1', 'busy', None)
        self.add_device('dev2', state='ready')

        # time out 20 times before finally heading back to try a new device
        for _ in range(20):
            self.assert_state('pending')
            self.driver.handle_timeout(self.req_id)

        # device is released and we're back to looking for a device and contacting
        # lifeguard.  This is contacting lifegaurd about dev2, since it's ready.
        self.assert_state('contact_lifeguard')
        self.assertEqual(self.db.device_requests.get_by_device('dev1'), None)

    def test_pending_result_timeout_failed_specific_device(self):
        # in this case, the request is for 'a specific device', so it never
        # times out (and would rely on the request being closed in practice)
        self.req_id = self.add_request(image='img1', device='dev1')

        self.set_state('pending')
        self.db.devices.set_machine_state('dev1', 'busy', None)
        self.add_device('dev2', state='ready')

        # run for more iterations than the state would otherwise, and see that
        # it doesn't ever go to contact_lifeguard
        iters = requestmachine.pending.PERMANENT_FAILURE_COUNT + 5
        for _ in range(iters):
            self.assert_state('pending')
            self.driver.handle_timeout(self.req_id)
