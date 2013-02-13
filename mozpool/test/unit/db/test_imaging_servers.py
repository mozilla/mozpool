# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.db import exceptions
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    img1 = {u'boot_config_keys': [u'a'],
            u'name': u'i1',
            u'id': 10,
            u'has_sut_agent': True,
            u'can_reuse': False,
            u'hidden': False}
    img2 = {u'boot_config_keys': [u'b'],
            u'name': u'i2',
            u'id': 11,
            u'has_sut_agent': False,
            u'can_reuse': True,
            u'hidden': True}

    def setUp(self):
        super(Tests, self).setUp()

    def test_get_id(self):
        id = self.add_server('ss')
        self.assertEqual(self.db.imaging_servers.get_id('ss'), id)

    def test_get_id_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.imaging_servers.get_id('ss'))

    def test_list(self):
        self.add_server('s1')
        self.add_server('s2')
        self.assertEqual(sorted(self.db.imaging_servers.list()), ['s1', 's2'])
