# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
import threading
import traceback
from mozpool.db import data
from mozpool.bmm import relay

def start_powercycle(device_name, callback, max_time=30):
    """
    Initiate a power cycle for DEVICE_NAME.  This function returns immediately,
    and will invoke CALLBACK with a boolean success indication when the
    operation is complete.  CALLBACK will be invoked in a different thread from
    that where this function was called.

    The function guarantees to callback before MAX_TIME seconds have elapsed,
    or not call back at all.
    """
    callback_before = time.time() + max_time

    # TODO: call this in the thread so it doesn't block and gets counted in the
    # total request time
    hostname, bnk, rly = data.board_relay_info(device_name)

    # TODO: verify this device belongs to this imaging server

    def try_powercycle():
        res = False
        try:
            res = relay.powercycle(hostname, bnk, rly, max_time)
        except:
            traceback.print_exc()
            print "(ignored)"

        if time.time() < callback_before:
            callback(res)
    threading.Thread(target=try_powercycle).start()
