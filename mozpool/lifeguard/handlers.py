# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton
import web
from mozpool import config
from mozpool.db import data
from mozpool.bmm import api as bmm_api
import mozpool.lifeguard

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  # /device methods
  "/device/([^/]+)/state-change/([^/]+)/to/([^/]+)/?", "state_change",
  "/device/([^/]+)/bootcomplete/?", "device_bootcomplete",
  "/device/([^/]+)/config/?", "device_config",
)

def deviceredirect(function):
    """
    Generate a redirect when a request is made for a device that is not
    managed by this instance of the service.
    """
    def wrapped(self, id, *args):
        try:
            server = data.get_server_for_device(id)
        except data.NotFound:
            raise web.notfound()
        if server != config.get('server', 'fqdn'):
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

# device handlers
class state_change:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name, from_state, to_state):
        # TODO: verify we own this device
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

class device_bootcomplete:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, name):
        # TODO: verify we own this device
        bmm_api.clear_pxe(name)
        return {}

class device_config:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.device_config(id)

