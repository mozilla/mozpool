# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton
import web
import mozpool.lifeguard
from mozpool.web.handlers import deviceredirect

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  "/device/([^/]+)/event/([^/]+)/?", "event",
  "/device/([^/]+)/state-change/([^/]+)/to/([^/]+)/?", "state_change",
)

# device handlers

class state_change:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name, from_state, to_state):
        args, body = templeton.handlers.get_request_parms()
        if 'pxe_config' in body:
            pxe_config = body['pxe_config']
            boot_config = body.get('boot_config', '')
        else:
            pxe_config = None
            boot_config = None
        success = mozpool.lifeguard.driver.conditional_state_change(
            device_name, from_state, to_state, pxe_config, boot_config) 
        if not success:
            raise web.conflict()
        return {}

class event:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name, event):
        args, body = templeton.handlers.get_request_parms()
        mozpool.lifeguard.driver.handle_event(device_name, event, body)
        return {}

    @deviceredirect
    @templeton.handlers.json_response
    def GET(self, device_name, event):
        mozpool.lifeguard.driver.handle_event(device_name, event, {})
        return {}

