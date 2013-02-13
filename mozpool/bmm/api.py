# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
from mozpool.async import wait_for_async, run_async
from mozpool.bmm import relay
from mozpool.bmm import pxe
from mozpool.bmm import sut
from mozpool.bmm import ping as ping_module

class API(object):

    def __init__(self, db):
        self.db = db

    def start_powercycle(self, device_name, callback, max_time=30):
        """
        Initiate a power cycle for DEVICE_NAME.  This function returns immediately,
        and will invoke CALLBACK with a boolean success indication when the
        operation is complete.  CALLBACK will be invoked in a different thread from
        that where this function was called.

        The function guarantees to callback before MAX_TIME seconds have elapsed,
        or not call back at all.
        """
        callback_before = time.time() + max_time
        hostname, bnk, rly = self.db.devices.get_relay_info(device_name)
        run_async(callback_before, callback,
                  lambda : relay.powercycle(hostname, bnk, rly, max_time))

    def powercycle(self, device_name, max_time=30):
        """Like start_powercycle, but block until completion and return the success
        status"""
        return wait_for_async(lambda cb :
                self.start_powercycle(device_name, cb, max_time))

    def start_poweroff(self, device_name, callback, max_time=30):
        """
        Initiate a power-off operation for DEVICE_NAME.  This function returns
        immediately, and will invoke CALLBACK with a boolean success indication
        when the operation is complete.  CALLBACK will be invoked in a different
        thread from that where this function was called.

        Use `start_powercycle` to turn power back on.

        The function guarantees to callback before MAX_TIME seconds have elapsed,
        or not call back at all.
        """
        callback_before = time.time() + max_time
        hostname, bnk, rly = self.db.devices.get_relay_info(device_name)
        run_async(callback_before, callback,
                lambda : relay.set_status(hostname, bnk, rly, False, max_time))

    def poweroff(self, device_name, max_time=30):
        """Like start_poweroff, but block until completion and return the success
        status"""
        return wait_for_async(lambda cb :
                self.start_poweroff(device_name, cb, max_time))

    def set_pxe(self, device_name, pxe_config_name):
        """
        Set the boot configuration for the given device to the start up with PXE
        config from PXE_CONFIG_NAME and supply an additional JSON configuration BOOT_CONFIG.
        """
        pxe_config = self.db.pxe_configs.get(pxe_config_name)['contents']
        mac_address = self.db.devices.get_mac_address(device_name)
        pxe.set_pxe(mac_address, pxe_config)

    def clear_pxe(self, device_name):
        """
        Clear a device's boot configuration, allowing it to boot from its internal
        storage.
        """
        mac_address = self.db.devices.get_mac_address(device_name)
        pxe.clear_pxe(mac_address)

    def start_ping(self, device_name, callback):
        """
        Begin pinging the device (using its fqdn, thus depending on DNS as well).
        The callback will be invoked with a boolean success flag within ten seconds.
        """
        callback_before = time.time() + 10
        fqdn = self.db.devices.get_fqdn(device_name)
        run_async(callback_before, callback,
                  lambda : ping_module.ping(fqdn))

    def ping(self, device_name):
        """Like ping, but block until completion and return the success
        status"""
        return wait_for_async(lambda cb :
                self.start_ping(device_name, cb))

    def start_reboot(self, device_name, callback):
        """
        Perform a reboot using SUT.

        The callback will be invoked within 45 seconds.
        """
        self.db.devices.log_message(device_name, 'starting reboot', 'sut')
        run_async(None, callback,
                lambda: sut.reboot(self.db.devices.get_fqdn(device_name)))

    def start_sut_verify(self, device_name, callback):
        """
        Verify the device using SUT.

        The callback will be invoked within 195 seconds.
        """
        self.db.devices.log_message(device_name, 'connecting to SUT agent', 'sut')
        run_async(None, callback,
                lambda: sut.sut_verify(self.db.devices.get_fqdn(device_name)))

    def start_check_sdcard(self, device_name, callback):
        """
        Verify the device's sdcard using SUT.

        The callback will be invoked within 30 seconds.
        """
        self.db.devices.log_message(device_name, 'verifying SD card', 'sut')
        run_async(None, callback,
                lambda: sut.check_sdcard(self.db.devices.get_fqdn(device_name)))

