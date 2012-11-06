# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import web
from mozpool import config
from mozpool.db import data, logs
from mozpool.bmm import relay

def boardredirect(function):
    """
    Generate a redirect when a request is made for a board that is not
    managed by this instance of the service.
    """
    def wrapped(self, id, *args):
        try:
            server = data.get_server_for_board(id)
        except data.NotFound:
            raise web.notfound()
        if server != config.get('server', 'fqdn'):
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

def get_symlink_path(board):
    """
    Get the path where the PXE boot symlink should be placed
    for a specific board.
    """
    mac_address = data.mac_with_dashes(data.board_mac_address(board))
    symlink_dir = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg")
    return os.path.join(symlink_dir, "01-" + mac_address)

def boot(board, image, config_data):
    """
    Boot board into image and set config_data for it to use
    as part of the boot process.
    """
    # board has already been checked by @boardredirect.
    # bootimage_details will raise for a nonexistent image.
    image_details = data.bootimage_details(image)['details']

    # Set a few things in the database before writing to disk.
    data.set_board_config(board, config_data)
    data.set_board_status(board, "boot-initiated")
    logs.board_logs.add(board, "Attempting to boot into image %s" % image)
    image_fullpath = os.path.join(config.get('paths', 'image_store'),
                                  image_details["pxe_config_filename"])
    # Make the link to the PXE config in the proper location
    tftp_symlink = get_symlink_path(board)
    symlink_dir = os.path.dirname(tftp_symlink)
    if not os.path.isdir(symlink_dir):
        try:
            os.mkdir(symlink_dir)
        except:
            pass

    if image_fullpath.startswith(config.get('paths', 'tftp_root')):
        # Use a relative symlink, because TFTP might be chrooted
        image_fullpath = os.path.join(os.path.relpath(os.path.dirname(image_fullpath),
                                                      os.path.dirname(tftp_symlink)),
                                                      image_details["pxe_config_filename"])
    os.symlink(image_fullpath, tftp_symlink)
    # Now actually reboot the board.
    relay_hostname, bank_num, relay_num = data.board_relay_info(board)
    return relay.powercycle(relay_hostname, bank_num, relay_num)

def reboot(board):
    """
    Powercycle board using the relay controller that controls its power.
    """
    relay_hostname, bank_num, relay_num = data.board_relay_info(board)
    data.set_board_status(board, "rebooting")
    logs.board_logs.add(board, "Rebooted by /reboot command")
    return relay.powercycle(relay_hostname, bank_num, relay_num)

def bootcomplete(board):
    """Remove symlink for this board's MAC address from TFTP."""
    data.set_board_status(board, "boot-complete")
    logs.board_logs.add(board, "Boot completed")
    tftp_symlink = get_symlink_path(board)
    os.unlink(tftp_symlink)
