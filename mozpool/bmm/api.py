# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.async import async_operation
from mozpool.bmm import relay
from mozpool.bmm import pxe
from mozpool.bmm import sut
from mozpool.bmm import ping

class API(object):
    """
    This class represents a common access point for all BMM operations.

    Each operation is represented as an AsyncOperation instance, meaning that
    it can be called asynchronously as `api.operation.start(callback,
    ..args..)` or synchronously as `api.operation.run(..args..)`.

    The asynchronous invocation returns immediately, and will invoke CALLBACK
    with the result when the operation is complete, or not at all if the
    operation fails or takes longer than the configured time.
    CALLBACK will be invoked in a different thread from
    that where this function was called.

    The synchronous invocation is similar to the asynchronous invocation, but
    blocks until the operation is complete, raising TimeoutError if that takes
    too long.
    """

    def __init__(self, db):
        self.db = db

    @async_operation(max_time=11)
    def test_two_way_comms(self, relay_name):
        """
        Initiate a two way comms test operation for RELAY_NAME.  Returns True on success
        and False on error.
        """
        hostname = self.db.relay_boards.get_fqdn(relay_name)
        return relay.test_two_way_comms(hostname, 10)

    @async_operation(max_time=30)
    def powercycle(self, device_name):
        """
        Initiate a power-cycle for `device_name`. This will turn the device on
        if it is powered off.  Returns True on success and False on error.
        """
        hostname, bnk, rly = self.db.devices.get_relay_info(device_name)
        return relay.powercycle(hostname, bnk, rly, 30)

    @async_operation(max_time=30)
    def poweroff(self, device_name):
        """
        Initiate a power-off operation for DEVICE_NAME.  Returns True on success
        and False on error.
        """
        hostname, bnk, rly = self.db.devices.get_relay_info(device_name)
        return relay.set_status(hostname, bnk, rly, False, 30)

    @async_operation(max_time=5)
    def set_pxe(self, device_name, pxe_config_name):
        """
        Set the boot configuration for the given device to the start up with
        PXE config from PXE_CONFIG_NAME and supply an additional JSON
        configuration BOOT_CONFIG.
        """
        pxe_config = self.db.pxe_configs.get(pxe_config_name)['contents']
        mac_address = self.db.devices.get_mac_address(device_name)
        pxe.set_pxe(mac_address, pxe_config)

    @async_operation(max_time=5)
    def clear_pxe(self, device_name):
        """
        Clear a device's boot configuration, allowing it to boot from its
        internal storage.
        """
        mac_address = self.db.devices.get_mac_address(device_name)
        pxe.clear_pxe(mac_address)

    @async_operation(max_time=10)
    def ping(self, device_name):
        """
        Ping the device (using its fqdn, thus depending on DNS as well).  The
        callback will be invoked with a boolean success flag within ten
        seconds.
        """
        fqdn = self.db.devices.get_fqdn(device_name)
        return ping.ping(fqdn)

    @async_operation(max_time=45)
    def sut_reboot(self, device_name):
        """
        Perform a reboot using SUT.  Returns True on success and False on error.

        The callback will be invoked within 45 seconds.
        """
        self.db.devices.log_message(device_name, 'starting reboot', 'sut')
        return sut.reboot(self.db.devices.get_fqdn(device_name))

    @async_operation(max_time=195)
    def sut_verify(self, device_name):
        """
        Verify the device using SUT.  Returns True on success and False on
        error.

        The callback will be invoked within 195 seconds.
        """
        self.db.devices.log_message(device_name, 'connecting to SUT agent', 'sut')
        return sut.sut_verify(self.db.devices.get_fqdn(device_name))

    @async_operation(max_time=30)
    def check_sdcard(self, device_name):
        """
        Verify the device's sdcard using SUT.  Returns True on success and
        False on error.

        The callback will be invoked within 30 seconds.
        """
        self.db.devices.log_message(device_name, 'verifying SD card', 'sut')
        return sut.check_sdcard(self.db.devices.get_fqdn(device_name))

