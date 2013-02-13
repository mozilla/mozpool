# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import posixpath
import tempfile
import traceback
from mozdevice import DeviceManagerSUT, DMError

logger = logging.getLogger('sut.cli')

def sut_verify(device_fqdn):
    # This should take no longer than 30 seconds (maximum 15 for connecting
    # and maximum 15 for the built-in call to get the device's test root).
    logger.info('Verifying that SUT agent is running.')
    DeviceManagerSUT.default_timeout = 15
    try:
        DeviceManagerSUT(device_fqdn, retryLimit=1)
    except DMError:
        logger.error('Exception initiating DeviceManager!')
        logger.error(traceback.format_exc())
        return False
    logger.info('Successfully connected to SUT agent.')
    return True

def check_sdcard(device_fqdn):
    # This should take a maximum of 13 SUT commands (some DM functions send
    # multiple commands).  Assuming worst-case scenario in which each one
    # takes the maximum timeout, that's 13 * 15 = 195 seconds.
    # Note that most of the time it will take much less.
    logger.info('Checking SD card.')
    success = True
    DeviceManagerSUT.default_timeout = 15
    try:
        dm = DeviceManagerSUT(device_fqdn)
        dev_root = dm.getDeviceRoot()
        if dev_root:
            d = posixpath.join(dev_root, 'sdcardtest')
            dm.removeDir(d)
            dm.mkDir(d)
            if dm.dirExists(d):
                with tempfile.NamedTemporaryFile() as tmp:
                    tmp.write('autophone test\n')
                    tmp.flush()
                    dm.pushFile(tmp.name, posixpath.join(d, 'sdcard_check'))
                    dm.removeDir(d)
                logger.info('Successfully wrote test file to SD card.')
            else:
                logger.error('Failed to create directory under device '
                             'root!')
                success = False
        else:
            logger.error('Invalid device root.')
            success = False
    except DMError:
        logger.error('Exception while checking SD card!')
        logger.error(traceback.format_exc())
        success = False
    return success

def reboot(device_fqdn):
    logger.info('Rebooting device via SUT agent.')
    # This guarantees that the total time will be about 45 seconds or less:
    # up to 15 seconds to connect, up to 15 seconds to get the device root,
    # and up to another 15 seconds to send the reboot command.
    DeviceManagerSUT.default_timeout = 15
    try:
        dm = DeviceManagerSUT(device_fqdn, retryLimit=1)
        dm.reboot()
    except DMError:
        logger.error('Reboot failed: %s' % traceback.format_exc())
        return False
    return True
