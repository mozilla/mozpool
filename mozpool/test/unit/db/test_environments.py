# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.add_server('server')
        self.add_device('dev1', environment='aa')
        self.add_device('dev2', environment='bb')
        self.add_device('dev3', environment='bb')

    def test_list(self):
        self.assertEqual(sorted(self.db.environments.list()), ['aa', 'bb'])
