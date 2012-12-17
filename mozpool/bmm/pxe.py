# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import logging
from mozpool import config
from mozpool.db import data

logger = logging.getLogger('bmm.pxe')

def _get_device_config_path(device_name):
    """
    Get the path where the PXE boot symlink should be placed
    for a specific device.
    """
    mac_address = data.mac_with_dashes(data.device_mac_address(device_name))
    symlink_dir = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg")
    return os.path.join(symlink_dir, "01-" + mac_address)

def set_pxe(device_name, pxe_config_name, boot_config):
    """
    Set up the PXE configuration for the device as directed.  Note that this does *not*
    reboot the device.
    """
    logger.info('setting pxe config for %s to %s%s' % (device_name, pxe_config_name,
        ' with boot config' if boot_config else ''))
    image_details = data.pxe_config_details(pxe_config_name)['details']
    pxe_config_contents = image_details['contents']

    # Write out the config file
    device_config_path = _get_device_config_path(device_name)
    device_config_dir = os.path.dirname(device_config_path)
    if not os.path.exists(device_config_dir):
        os.makedirs(device_config_dir)

    # apply ipaddress substitution to the config contents
    pxe_config_contents = pxe_config_contents.replace('%IPADDRESS%', config.get('server', 'ipaddress'))

    open(device_config_path, "w").write(pxe_config_contents)

def clear_pxe(device_name):
    """Remove config for this device's MAC address from TFTP."""
    logger.info('clearing pxe config for %s' % (device_name,))
    tftp_symlink = _get_device_config_path(device_name)
    if os.path.exists(tftp_symlink):
        os.unlink(tftp_symlink)
