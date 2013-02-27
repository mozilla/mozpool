# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy as sa
from mozpool.db import model, exceptions
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.add_image('img1')
        self.add_server('server1')
        self.add_device('dev1', server='server1')
        self.request_id = self.add_request(server='server1', image='img1',
                                           device='dev1', state='pending')

    def test_add(self):
        new_req_id = self.add_request(server='server1', image='img1', no_assign=True)
        new_dev_id = self.add_device('dev2', server='server1')

        q = sa.select([model.device_requests.c.request_id, model.device_requests.c.device_id])
        q = q.where(model.device_requests.c.request_id == new_req_id)

        self.assertEqual(self.db.execute(q).fetchall(), [])
        self.assertTrue(self.db.device_requests.add(new_req_id, 'dev2'))
        self.assertEqual(self.db.execute(q).fetchall(), [(new_req_id, new_dev_id)])

    def test_add_conflict(self):
        self.add_device('dev2', server='server1')
        # this request is already assigned to dev1
        self.assertFalse(self.db.device_requests.add(self.request_id, 'dev2'))

    def test_add_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.device_requests.add(self.request_id, 'dev2'))

    def test_clear(self):
        q = sa.select([model.device_requests.c.request_id])
        q = q.where(model.device_requests.c.request_id == self.request_id)
        self.assertEqual(self.db.execute(q).fetchall(), [(self.request_id,)])
        self.db.device_requests.clear(self.request_id)
        self.assertEqual(self.db.execute(q).fetchall(), [])

    def test_get_by_device(self):
        self.assertEqual(self.db.device_requests.get_by_device('dev1'),
                         self.request_id)

    def test_get_by_device_none(self):
        self.assertEqual(self.db.device_requests.get_by_device('dev2'), None)

    def test_get_result_none(self):
        self.assertEqual(self.db.device_requests.get_result(self.request_id), None)
        self.assertEqual(self.db.device_requests.get_result(99), None)

    def test_set_get_result(self):
        self.db.device_requests.set_result('dev1', 'in prog')
        self.assertEqual(self.db.device_requests.get_result(self.request_id), 'in prog')

    def test_set_result_notfound(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.device_requests.set_result('dev99', 'in prog'))
