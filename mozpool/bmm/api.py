# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
import threading

def start_powercycle(device_name, callback):
    """
    Initiate a power cycle for DEVICE_NAME.  This function returns immediately,
    and will invoke CALLBACK with a boolean success indication when the
    operation is complete.  CALLBACK will be invoked in a different thread from
    that where this function was called.
    """

    # TODO: this needs to guarantee to complete within some specific time

    # fake for now
    def sleep_and_callback():
        time.sleep(1)
        callback(True)
    threading.Thread(target=sleep_and_callback).start()
