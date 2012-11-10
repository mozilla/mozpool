# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import time
import threading
from mozpool.db import data
from mozpool.db import logs
from mozpool.bmm import relay
from mozpool.bmm import pxe
from mozpool.bmm import ping as ping_module

def _wait_for_async(start_fn):
    done_cond = threading.Condition()

    cb_result = []
    def cb(arg):
        cb_result.append(arg)
        done_cond.acquire()
        done_cond.notify()
        done_cond.release()

    done_cond.acquire()
    start_fn(cb)
    done_cond.wait()
    done_cond.release()

    return cb_result[0]

logger = logging.getLogger('bmm.api')

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

    hostname, bnk, rly = data.device_relay_info(device_name)

    logs.device_logs.add(device_name, "initiating power cycle")
    def try_powercycle():
        res = False
        try:
            res = relay.powercycle(hostname, bnk, rly, max_time)
        except:
            logger.error("(ignored) exception while running powercycle", exc_info=True)

        if time.time() < callback_before:
            callback(res)
    threading.Thread(target=try_powercycle).start()

def powercycle(device_name, max_time=30):
    """Like start_powercycle, but block until completion and return the success
    status"""
    return _wait_for_async(lambda cb :
            start_powercycle(device_name, cb, max_time))

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

def start_ping(device_name, callback):
    """
    Begin pinging the device (using its fqdn, thus depending on DNS as well).
    The callback will be invoked with a boolean success flag within ten seconds.
    """
    callback_before = time.time() + 10
    fqdn = data.device_fqdn(device_name)

    def try_ping():
        try:
            pingable = ping_module.ping(fqdn)
        except:
            logger.error("(ignored) exception while running powercycle", exc_info=True)
            pingable = False

        logs.device_logs.add(device_name, "ping of %s complete: %s" % (fqdn, 'ok' if pingable else 'failed'))
        if time.time() < callback_before:
            callback(pingable)
    threading.Thread(target=try_ping).start()

def ping(device_name):
    """Like ping, but block until completion and return the success
    status"""
    return _wait_for_async(lambda cb :
            start_ping(device_name, cb))
