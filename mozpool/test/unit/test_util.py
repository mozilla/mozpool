# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import threading
from mozpool import util
from mozpool.test.util import TestCase

class Tests(TestCase):

    def test_LocksByName_different_names(self):
        # this just needs to not deadlock..
        self.lbn = util.LocksByName()
        self.lbn.acquire('one')
        self.lbn.acquire('two')
        self.lbn.release('one')
        self.lbn.release('two')

    def test_LocksByName_same_name(self):
        self.lbn = util.LocksByName()
        events = []
        self.lbn.acquire('one')
        events.append('this locked')
        def other_thread():
            events.append('other started')
            self.lbn.acquire('one')
            events.append('other locked')
            self.lbn.release('one')
            events.append('other unlocked')
        thd = threading.Thread(target=other_thread)
        thd.start()
        # busywait for the thread to start
        while 'other started' not in events:
            pass
        events.append('unlocking this')
        self.lbn.release('one')
        thd.join()

        self.assertEqual(events,
            [ 'this locked', 'other started', 'unlocking this', 'other locked', 'other unlocked' ])

        def test_from_json(self):
            self.assertEqual(util.from_json('{"a": "b"}'), {'a': 'b'})
            self.assertEqual(util.from_json('{"a"'), {})

        def test_mac_with_dashes(self):
            self.assertEqual(util.mac_with_dashes('112233445566', '11-22-33-44-55-66'))
