# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import time
import mock
from mozpool import async
from mozpool.test.util import TestCase

class API(object):

    @async.async_operation(max_time=0.05)
    def operation(self, addend1, addend2, factor=1, stall=False, fail=False):
        if stall:
            time.sleep(0.1)
        if fail:
            raise RuntimeError('oh noes')
        return (addend1 + addend2) * factor


class Tests(TestCase):

    def setUp(self):
        self.api = API()

    def test_async_run(self):
        self.assertEqual(self.api.operation.run(10, 20, factor=3), 90)

    def test_async_run_stall(self):
        self.assertRaises(async.TimeoutError, lambda :
                self.api.operation.run(10, 20, stall=True))

    def test_start(self):
        self.res = None
        def cb(res):
            self.res = res
        self.api.operation.start(cb, 10, 20)

        # just busyloop until we get a result or 1s elapses
        start = time.time()
        while not self.res and time.time() - start < 1:
            time.sleep(0.001)
        self.assertEqual(self.res, 30)

    def test_start_stall(self):
        self.res = None
        def cb(res):
            self.res = res
        self.api.operation.start(cb, 10, 20, stall=True)
        time.sleep(0.15)
        # callback should not have been called
        self.assertEqual(self.res, None)

    def test_start_fail(self):
        self.res = None
        def cb(res):
            self.res = res
        self.api.operation.start(cb, 10, 20, fail=True)
        time.sleep(0.15)
        # callback should not have been called
        self.assertEqual(self.res, None)

class RequestsTests(TestCase):

    @mock.patch('requests.get')
    def test_get(self, get):
        async.requests.get.run('foo')
        get.assert_called_with('foo', timeout=30)

    @mock.patch('requests.post')
    def test_post(self, post):
        async.requests.post.run('foo', 'DATA')
        post.assert_called_with('foo', data='DATA', timeout=30)
