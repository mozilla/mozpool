# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from mozpool.async import run_async
from mozpool.db import data, logs
from mozpool.sut import cli

logger = logging.getLogger('sut.api')

# Asynchronous wrappers for DeviceManagerSUT functions.
# We don't bother with callback timeouts because DeviceManagerSUT takes
# care of all timeouts internally.

def start_reboot(device_name, callback):
    logger.info('Starting reboot.')
    logs.device_logs.add(device_name, 'starting reboot', 'sut')
    run_async(None, callback,
              lambda: cli.reboot(data.device_fqdn(device_name)), logger)

def start_sut_verify(device_name, callback):
    logger.info('Verifying SUT agent.')
    logs.device_logs.add(device_name, 'connecting to SUT agent', 'sut')
    run_async(None, callback,
              lambda: cli.sut_verify(data.device_fqdn(device_name)), logger)

def start_check_sdcard(device_name, callback):
    logger.info('Starting SD-card check.')
    logs.device_logs.add(device_name, 'verifying SD card', 'sut')
    run_async(None, callback,
              lambda: cli.check_sdcard(data.device_fqdn(device_name)), logger)
