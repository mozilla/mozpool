# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import threading

class LocksByName(object):
    """A collection of named locks, each individually lockable."""

    def __init__(self):
        self._locks_by_name = {}
        self._lock = threading.Lock()

    def acquire(self, name):
        with self._lock:
            try:
                lock = self._locks_by_name[name]
            except KeyError:
                lock = self._locks_by_name[name] = threading.Lock()
        lock.acquire()

    def release(self, name):
        with self._lock:
            lock = self._locks_by_name[name]
        lock.release()

