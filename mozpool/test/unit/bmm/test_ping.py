# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mock import patch
from mozpool.bmm import ping
from mozpool.test.util import TestCase

class Tests(TestCase):

    fixed_args = '-q -r4 -t50'

    @patch("os.system")
    def test_ping_success(self, system):
        system.return_value = 0
        self.assertTrue(ping.ping('abcd'))
        system.assert_called_with('fping %s abcd' % self.fixed_args)

    @patch("os.system")
    def test_ping_fails(self, system):
        system.return_value = 256
        self.assertFalse(ping.ping('abcd'))
        system.assert_called_with('fping %s abcd' % self.fixed_args)
