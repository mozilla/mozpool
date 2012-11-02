# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton
from mozpool.db import data
from mozpool.bmm import board
from mozpool.bmm.board import boardredirect

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  # /board methods
  "/board/list/?", "board_list",
  "/board/([^/]+)/status/?", "board_status",
  "/board/([^/]+)/boot/([^/]+)/?", "board_boot",
  "/board/([^/]+)/reboot/?", "board_reboot",
  "/board/([^/]+)/bootcomplete/?", "board_bootcomplete",
  "/board/([^/]+)/config/?", "board_config",
  # /bootimage methods
  "/bootimage/list/?", "bootimage_list",
  "/bootimage/([^/]+)/details/?", "bootimage_details",
)

# board handlers
class board_list:
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        if 'details' in args:
            return dict(boards=data.dump_boards())
        else:
            return data.list_boards()

class board_status:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.board_status(id)

    @templeton.handlers.json_response
    def POST(self, id):
        args, body = templeton.handlers.get_request_parms()
        return {"status": data.set_board_status(id, body["status"])}

class board_boot:
    @boardredirect
    @templeton.handlers.json_response
    def POST(self, id, image):
        args, body = templeton.handlers.get_request_parms()
        board.boot(id, image, body)
        return {}

class board_reboot:
    @boardredirect
    @templeton.handlers.json_response
    def POST(self, id):
        board.reboot(id)
        return {}

class board_bootcomplete:
    @boardredirect
    @templeton.handlers.json_response
    def POST(self, id):
        board.bootcomplete(id)
        return {}

class board_config:
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
