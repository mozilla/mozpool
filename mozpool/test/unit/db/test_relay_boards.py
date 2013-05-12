# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.db import exceptions
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.add_server('server1')
        self.add_server('server2')
        self.add_relay_board(relay_board='relay1', server='server1', dn='.fqdn')
        self.add_relay_board(relay_board='relay2', server='server2', dn='.example')

    def test_get_fqdn(self):
        self.assertEqual(self.db.relay_boards.get_fqdn('relay1'), 'relay1.fqdn')
        self.assertEqual(self.db.relay_boards.get_fqdn('relay2'), 'relay2.example')

    def test_get_fqdn_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.relay_boards.get_fqdn('relay404'))

    def test_get_imaging_server(self):
        self.assertEqual(self.db.relay_boards.get_imaging_server('relay1'), 'server1')
        self.assertEqual(self.db.relay_boards.get_imaging_server('relay2'), 'server2')

    def test_get_imaging_server_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.relay_boards.get_imaging_server('relay404'))
