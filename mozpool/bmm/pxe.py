# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from mozpool import config
from mozpool import util

def _get_device_config_path(mac_address):
    """
    Get the path where the PXE boot symlink should be placed
    for a specific device.
    """
    mac_address = util.mac_with_dashes(mac_address)
    symlink_dir = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg")
    return os.path.join(symlink_dir, "01-" + mac_address)

def set_pxe(mac_address, pxe_config):
    """
    Set up the PXE configuration for the device as directed, substituting the
    server's IP address.  Note that this does *not* reboot the device.
    """
    # Write out the config file
    device_config_path = _get_device_config_path(mac_address)
    device_config_dir = os.path.dirname(device_config_path)
    if not os.path.exists(device_config_dir):
        os.makedirs(device_config_dir)

    # apply ipaddress substitution to the config contents
    pxe_config_contents = pxe_config.replace('%IPADDRESS%', config.get('server', 'ipaddress'))

    open(device_config_path, "w").write(pxe_config_contents)

def clear_pxe(mac_address):
    """Remove config for this device's MAC address from TFTP."""
    tftp_symlink = _get_device_config_path(mac_address)
    if os.path.exists(tftp_symlink):
        os.unlink(tftp_symlink)
