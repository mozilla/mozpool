# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from mozpool import config
from mozpool.db import data

def _get_symlink_path(device_name):
    """
    Get the path where the PXE boot symlink should be placed
    for a specific device.
    """
    mac_address = data.mac_with_dashes(data.board_mac_address(device_name))
    symlink_dir = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg")
    return os.path.join(symlink_dir, "01-" + mac_address)

def set_pxe(device_name, image_name, config_data):
    """
    Set up the PXE configuration for the device as directed.  Note that this does *not*
    reboot the device.
    """
    image_details = data.bootimage_details(image_name)['details']
    pxe_config_filename = image_details['pxe_config_filename']

    # Set the config in the database before writing to disk.
    data.set_board_config(device_name, config_data)
    image_fullpath = os.path.join(config.get('paths', 'image_store'), pxe_config_filename)

    # Make the link to the PXE config in the proper location
    tftp_symlink = _get_symlink_path(device_name)
    symlink_dir = os.path.dirname(tftp_symlink)
    if not os.path.isdir(symlink_dir):
        try:
            os.mkdir(symlink_dir)
        except:
            pass

    if image_fullpath.startswith(config.get('paths', 'tftp_root')):
        # Use a relative symlink, because TFTP might be chrooted
        print "HERE"
        image_fullpath = os.path.join(os.path.relpath(os.path.dirname(image_fullpath),
                                                      os.path.dirname(tftp_symlink)),
                                                      pxe_config_filename)
    os.symlink(image_fullpath, tftp_symlink)

def clear_pxe(device_name):
    """Remove symlink for this device's MAC address from TFTP."""
    tftp_symlink = _get_symlink_path(device_name)
    if os.path.exists(tftp_symlink):
        os.unlink(tftp_symlink)
