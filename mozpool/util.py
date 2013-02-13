# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import threading
from itertools import izip_longest

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

def from_json(s):
    """
    Converts JSON string 's' to an object but also handles empty/bad values.
    """
    try:
        return json.loads(s)
    except ValueError:
        return {}

def mac_with_dashes(mac):
    """
    Reformat a 12-digit MAC address to contain
    a dash between each 2 characters.
    """
    # From the itertools docs.
    return "-".join("%s%s" % i for i in izip_longest(fillvalue=None, *[iter(mac)]*2))

