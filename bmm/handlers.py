# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import socket
import templeton
import web
from bmm import data
from bmm import board
from bmm.board import boardredirect

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  # /board methods
  "/board/list/?", "board_list",
  "/board/([^/]+)/status/?", "board_status",
  "/board/([^/]+)/boot/([^/]+)/?", "board_boot",
  "/board/([^/]+)/reboot/?", "board_reboot",
  "/board/([^/]+)/config/?", "board_config",
  # /bootimage methods
  "/bootimage/list/?", "bootimage_list",
  "/bootimage/([^/]+)/details/?", "bootimage_details",
)

# board handlers
class board_list:
    @templeton.handlers.json_response
    def GET(self):
        try:
            return data.list_boards_for_imaging_server(socket.getfqdn())
        except data.NotFound:
            return {'boards':{}}

class board_status:
    @boardredirect
    @templeton.handlers.json_response
    def GET(self, id):
        return data.board_status(id)

    @boardredirect
    @templeton.handlers.json_response
    def POST(self, id):
        args, body = templeton.handlers.get_request_parms()
        return {"state": data.set_board_status(id, body['state'])}

class board_boot:
    @boardredirect
    def POST(self, id, image):
        args, body = templeton.handlers.get_request_parms()
        board.boot(id, image, body)
        return "" #XXX: should we return something here?

class board_reboot:
    @boardredirect
    def POST(self, id):
        board.reboot(id)
        #XXX: should we return something here?
        raise web.webapi._status_code("204 No Content")

class board_config:
    @boardredirect
    @templeton.handlers.json_response
    def GET(self, id):
        return data.board_config(id)

# bootimage handlers
class bootimage_list:
    @templeton.handlers.json_response
    def GET(self):
        return data.list_bootimages()

class bootimage_details:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.bootimage_details(id)
