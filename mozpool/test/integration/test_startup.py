# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import traceback
import multiprocessing
from mozpool import config
from mozpool.test.util import TestCase


class RemoteError(Exception):
    pass


class Tests(TestCase):

    def setUp(self):
        self.process = None

    def tearDown(self):
        if self.process:
            self.process.terminate()
            self.process.join()

    def run_in_subprocess(self, fn):
        q = multiprocessing.Queue()
        def do():
            try:
                fn()
                q.put(None)
            except:
                q.put(traceback.format_exc())
        self.process = multiprocessing.Process(target=do)
        self.process.start()
        # if there was an exception in the child process, there's an exception
        # in the parent process, too, although not very well-matched.
        e = q.get()
        self.process.join()
        if e:
            print e
            raise RemoteError()

    def test_web_server_main(self):
        def call_main():
            from mozpool.web import server
            # configure an invalid DB - startup should succeed anyway
            config.reset()
            config.set('database', 'engine', 'sqlite://////')
            server.main(run=False)
        self.run_in_subprocess(call_main)
