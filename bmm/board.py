# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import socket
import threading
import web
from bmm import config
from bmm import data
from bmm import relay

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
    data.add_log(board, "Attempting to boot into image %s" % image)
    image_fullpath = os.path.join(config.get('paths', 'image_store'),
                                  image_details["pxe_config_filename"])
    # Make the link to the PXE config in the proper location
    mac_address = data.mac_with_dashes(data.board_mac_address(board))
    symlink_dir = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg")
    if not os.path.isdir(symlink_dir):
        try:
            os.mkdir(symlink_dir)
        except:
            pass
    tftp_symlink = os.path.join(symlink_dir, "01-" + mac_address)
    #print "Linking %s -> %s" % (image_fullpath, tftp_symlink)
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
    data.add_log(board, "Rebooted by /reboot command")
    return relay.powercycle(relay_hostname, bank_num, relay_num)
