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
        if server != config.server_fqdn():
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

def boot_thread(board, tftp_symlink, pxe_config_filename):
    """
    Run on a background thread to perform the long-running work of
    actually rebooting a board into a boot image.
    """
    # First, reboot the board.
    relay_hostname, bank_num, relay_num = data.board_relay_info(board)
    relay.powercycle(relay_hostname, bank_num, relay_num)
    # Second, watch TFTP logs to see that the image was requested
    #   by the board.
    pass

def boot(board, image, config_data):
    # board has already been checked by @boardredirect.
    # bootimage_details will raise for a nonexistent image.
    image_details = data.bootimage_details(image)['details']

    # The split of work between this method and the boot_thread
    # is somewhat arbitrary. Prefer to do all the simple database and file
    # work here before launching the thread to do the powercycle and
    # log-watching.
    data.set_board_config(board, config_data)
    data.set_board_status(board, "boot-initiated")
    data.add_log(board, "Attempting to boot into image %s" % image)
    image_fullpath = os.path.join(config.image_store(),
                                  image_details["pxe_config_filename"])
    # Make the link to the PXE config in the proper location
    mac_address = data.board_mac_address(board)
    #FIXME: 'pxelinux.cfg/01-2a-40-fe-d5-3b-0a'
    tftp_symlink = os.path.join(config.tftp_root(), mac_address)
    print "Linking %s -> %s" % (image_fullpath, tftp_symlink)
    os.symlink(image_fullpath, tftp_symlink)
    t = threading.Thread(target=boot_thread, args=(board,
                                                   tftp_symlink,
                                                   image_fullpath))
    t.start()

def reboot(board):
    relay_hostname, bank_num, relay_num = data.board_relay_info(board)
    data.set_board_status(board, "rebooting")
    data.add_log(board, "Rebooted by /reboot command")
    return relay.powercycle(relay_hostname, bank_num, relay_num)
