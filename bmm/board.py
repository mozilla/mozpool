# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import socket
import web
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
        if server != socket.getfqdn():
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

def boot(id, image, config):
    #TODO
    pass

def reboot(id):
    relay_hostname, bank_num, relay_num = data.board_relay_info(id)
    data.set_board_status(id, "rebooting")
    data.add_log(id, "Rebooted by /reboot command")
    return relay.powercycle(relay_hostname, bank_num, relay_num)
