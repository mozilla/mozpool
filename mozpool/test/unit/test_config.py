# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import os
import textwrap
import mock
from mozpool import config
from mozpool.test.util import DirMixin, TestCase

class Tests(DirMixin, TestCase):

    def test_get_set(self):
        config.reset()
        config.set('abc', 'def', 'ghi')
        self.assertEqual(config.get('abc', 'def'), 'ghi')
        self.assertEqual(config.get('abc', 'XXX'), None)
        self.assertEqual(config.get('XXX', 'XXX'), None)

    def test_load_blank(self):
        # this might load anything from a test config.ini, so we don't assert
        # any values.  But it should succeed.
        config._config = None
        config._load()

    @mock.patch('socket.getfqdn')
    @mock.patch('socket.gethostbyname')
    def test_load(self, gethostbyname, getfqdn):
        getfqdn.return_value = 'server.example.com'
        gethostbyname.return_value = '1.2.3.4'

        cfg_file = os.path.join(self.tempdir, "cfg")
        open(cfg_file, "w").write(textwrap.dedent("""\
            [test]
            val1 = 1
            """))
        os.environ['MOZPOOL_CONFIG'] = cfg_file

        config._config = None
        config._load()

        # check defaults as well as the value in the config above
        self.assertEqual(config.get('server', 'fqdn'), 'server.example.com')
        self.assertEqual(config.get('server', 'ipaddress'), '1.2.3.4')
        self.assertEqual(config.get('test', 'val1'), '1')
