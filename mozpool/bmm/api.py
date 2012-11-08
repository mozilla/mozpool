# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
import threading
import traceback
from mozpool.db import data
from mozpool.db import logs
from mozpool.bmm import relay
from mozpool.bmm import pxe

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
    hostname, bnk, rly = data.device_relay_info(device_name)

    # TODO: verify this device belongs to this imaging server

    logs.device_logs.add(device_name, "initiating power cycle")
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

def powercycle(device_name, max_time=30):
    """Like start_powercycle, but block until completion and return the success
    status"""
    result = []
    cond = threading.Condition()

    def callback(success):
        result.append(success)
        cond.acquire()
        cond.notify()
        cond.release()

    cond.acquire()
    start_powercycle(device_name, callback, max_time)
    while not result:
        cond.wait()
    cond.release()

    return result[0]

def set_pxe(device_name, image_name, boot_config):
    """
    Set the boot configuration for the given device to the start up with PXE
    config from IMAGE_NAME and supply an additional JSON configuration BOOT_CONFIG.
    """
    logs.device_logs.add(device_name, "setting PXE config to image %s" % (image_name,))
    pxe.set_pxe(device_name, image_name, boot_config)

def clear_pxe(device_name):
    """
    Clear a device's boot configuration, allowing it to boot from its internal
    storage.
    """
    logs.device_logs.add(device_name, "clearing PXE config")
    pxe.clear_pxe(device_name)
