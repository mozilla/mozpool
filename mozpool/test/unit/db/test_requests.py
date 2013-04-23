# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
from mozpool.db import exceptions
from mozpool.test.util import DBMixin, ConfigMixin, TestCase

class Tests(DBMixin, ConfigMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.img_id = self.add_image('b2g')
        self.server_id = self.add_server('my_fqdn')
        self.add_server('server')
        self.req_id = self.add_request(server='my_fqdn', no_assign=True,
                expires=datetime.datetime(1978, 6, 15))

    def test_add(self):
        now = lambda : datetime.datetime(1978, 6, 15)
        request_id = self.db.requests.add(requested_device='any',
                environment='any', assignee='any', duration=3600,
                image_id=self.img_id, boot_config={}, _now=now)
        self.assertEqual(self.db.requests.get_info(request_id),
                {'environment': u'any',
                 'requested_device': u'any',
                 'boot_config': u'{}',
                 'assignee': u'any',
                 'image': u'b2g',
                 'expires': datetime.datetime(1978, 6, 15, 1, 0),
                 'id': request_id,
                 'assigned_device': ''})

    def test_renew(self):
        now = lambda : datetime.datetime(1978, 6, 15)
        self.db.requests.renew(self.req_id, 36000, _now=now)
        expires = self.db.requests.get_info(self.req_id)['expires']
        self.assertEqual(expires, datetime.datetime(1978, 6, 15, 10, 0))

    def test_list_expired(self):
        now = lambda : datetime.datetime(1978, 6, 15)
        def mkreq(offset, state, server):
            return self.add_request(server=server, no_assign=True,
                    expires=now() + datetime.timedelta(hours=offset),
                    state=state)
        req_ids = [
            mkreq(-1, 'pending', 'my_fqdn'), # good
            mkreq(-1, 'expired', 'my_fqdn'), # expired state (convert to closed for compatibility)
            mkreq(10, 'pending', 'my_fqdn'), # not expired
            mkreq(-1, 'closed', 'my_fqdn'), # closed state
            mkreq(-1, 'failed_borked', 'my_fqdn'), # failed state
            mkreq(-1, 'pending', 'server'), # other server
        ]
        self.assertEqual(self.db.requests.list_expired(self.server_id, _now=now),
                         req_ids[:2])

    def test_get_imaging_server(self):
        self.assertEqual(self.db.requests.get_imaging_server(self.req_id), 'my_fqdn')

    def test_get_imaging_server_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.requests.get_imaging_server(99))

    def test_list(self):
        open_req = {
            u'assigned_device': '',
            u'assignee': u'slave',
            u'boot_config': u'{}',
            u'device_state': '',
            u'environment': None,
            u'expires': datetime.datetime(1978, 6, 15),
            u'id': self.req_id,
            u'imaging_server': u'my_fqdn',
            u'requested_device': u'any',
            u'state': u'new'}
        self.add_device('dev1', state='sleeping')
        closed_id = self.add_request(device='dev1', state='closed',
                expires=datetime.datetime(1978, 6, 2))
        closed_req = {
            u'assigned_device': u'',
            u'assignee': u'slave',
            u'boot_config': u'{}',
            u'device_state': u'',
            u'environment': None,
            u'expires': datetime.datetime(1978, 6, 2),
            u'id': closed_id,
            u'imaging_server': u'server',
            u'requested_device': u'dev1',
            u'state': u'closed'}
        self.add_device('dev2', state='snoring')
        assigned_id = self.add_request(device='dev2', state='assigned',
                expires=datetime.datetime(1978, 6, 3))
        assigned_req = {
            u'assigned_device': u'dev2',
            u'assignee': u'slave',
            u'boot_config': u'{}',
            u'device_state': u'snoring',
            u'environment': None,
            u'expires': datetime.datetime(1978, 6, 3),
            u'id': assigned_id,
            u'imaging_server': u'server',
            u'requested_device': u'dev2',
            u'state': u'assigned'}
        self.assertEqual(sorted(self.db.requests.list()),
                    sorted([open_req, assigned_req]))
        self.assertEqual(sorted(self.db.requests.list(include_closed=True), key=lambda x:x['id']),
                sorted([open_req, closed_req, assigned_req], key=lambda x:x['id']))

    def test_get_assigned_device(self):
        self.add_device('dev1')
        req_id = self.add_request(device='dev1')
        self.assertEqual(self.db.requests.get_assigned_device(req_id), 'dev1')

    def test_get_assigned_device_missing_request(self):
        self.assertEqual(self.db.requests.get_assigned_device(99), None)

    def test_get_assigned_device_unassigned(self):
        self.assertEqual(self.db.requests.get_assigned_device(self.req_id), None)

    def test_get_info(self):
        self.assertEqual(self.db.requests.get_info(self.req_id),
                {'environment': None,
                 'requested_device': u'any',
                 'boot_config': u'{}',
                 'assignee': u'slave',
                 'image': u'b2g',
                 'expires': datetime.datetime(1978, 6, 15),
                 'id': self.req_id,
                 'assigned_device': ''})

    def test_get_info_assigned(self):
        self.add_device('dev2')
        assigned_id = self.add_request(device='dev2', state='assigned',
                expires=datetime.datetime(1978, 6, 3))
        self.assertEqual(self.db.requests.get_info(assigned_id),
                {'environment': None,
                 'requested_device': u'dev2',
                 'boot_config': u'{}',
                 'assignee': u'slave',
                 'image': u'b2g',
                 'expires': datetime.datetime(1978, 6, 3),
                 'id': assigned_id,
                 'assigned_device': 'dev2'})

    def test_get_info_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
            self.db.requests.get_info(99))


class TestStateMachineMethods(DBMixin, TestCase):

    # These methods are implemented with mixins, and are fully tested in
    # test_devices.py. This is just enough to make sure that requests.py sets
    # the class variables appropriately.

    def setUp(self):
        super(TestStateMachineMethods, self).setUp()
        self.add_server('server')
        self.add_image('b2g')
        self.req_id = self.add_request(no_assign=True, state='disarray')

    def test_get_machine_state(self):
        self.assertEqual(self.db.requests.get_machine_state(self.req_id), 'disarray')


class TestObjectLogsMethods(DBMixin, TestCase):

    # These methods are implemented with mixins, and are fully tested in
    # test_devices.py. This is just enough to make sure that requests.py sets
    # the class variables appropriately.

    def test_log_message_and_get_logs(self):
        self.assertEqual(sorted(self.db.requests.get_logs(1)), [])
