# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton
import web
import datetime
import time
import mozpool.lifeguard
from mozpool.web.handlers import deviceredirect, InMemCacheMixin, Handler

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  "/device/([^/]+)/event/([^/]+)/?", "device_event",
  "/device/([^/]+)/state-change/([^/]+)/to/([^/]+)/?", "state_change",
  "/device/([^/]+)/status/?", "device_status",
  "/device/([^/]+)/state/?", "device_state",
)

# device handlers

class state_change(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name, from_state, to_state):
        success = mozpool.lifeguard.driver.conditional_state_change(
                                        device_name, from_state, to_state)
        if not success:
            raise web.conflict()
        return {}

class device_event(Handler):
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

class device_status(Handler):
    @templeton.handlers.json_response
    def GET(self, device_name):
        state = self.db.devices.get_machine_state(device_name)
        logs = self.db.devices.get_logs(device_name, limit=100)
        return {'state': state, 'log': logs}

class device_state(Handler, InMemCacheMixin):
    CACHE_TTL = 5

    def update_cache(self):
        return self.db.devices.list_states()

    @templeton.handlers.json_response
    def GET(self, device_name):
        args, _ = templeton.handlers.get_request_parms()
        if args.get('cache'):
            # get state from a cache of all devices' state; this is used
            # for monitoring devices, so we don't pound the DB
            state = self.cache_get()[device_name]
            ttl = self.cache_expires - time.time()
            web.expires(datetime.timedelta(seconds=ttl))
            web.header('Cache-Control', 'public, max-age=%d' % int(ttl+1))
        else:
            # get the fresh state
            state = self.db.devices.get_machine_state(device_name)
        return { 'state' : state }

