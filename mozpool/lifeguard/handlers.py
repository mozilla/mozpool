# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton
import web
import datetime
import time
import mozpool.lifeguard
from mozpool.db import data
from mozpool.web.handlers import deviceredirect, InMemCache

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  "/device/([^/]+)/event/([^/]+)/?", "event",
  "/device/([^/]+)/state-change/([^/]+)/to/([^/]+)/?", "state_change",
  "/device/([^/]+)/status/?", "device_status",
  "/device/([^/]+)/state/?", "device_state",
)

# device handlers

class state_change:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name, from_state, to_state):
        success = mozpool.lifeguard.driver.conditional_state_change(
                                        device_name, from_state, to_state)
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

class device_status:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.device_status(id)

class device_state(InMemCache):
    CACHE_TTL = 5

    def update_cache(self):
        return data.all_device_states()

    @templeton.handlers.json_response
    def GET(self, id):
        state = self.cache_get()[id]
        ttl = self.cache_expires - time.time()
        web.expires(datetime.timedelta(seconds=ttl))
        web.header('Cache-Control', 'public, max-age=%d' % int(ttl+1))
        return { 'state' : state }

