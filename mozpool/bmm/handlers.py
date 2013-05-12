# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import web
import templeton
from mozpool.web.handlers import deviceredirect, relayredirect, Handler
from mozpool.bmm import api

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  "/device/([^/]+)/power-cycle/?", "power_cycle",
  "/device/([^/]+)/power-off/?", "power_off",
  "/device/([^/]+)/ping/?", "ping",
  "/device/([^/]+)/clear-pxe/?", "clear_pxe",
  "/device/([^/]+)/log/?", "device_log",
  "/device/([^/]+)/bootconfig/?", "device_bootconfig",
  "/device/([^/]+)/set-comments/?", "device_set_comments",
  "/device/([^/]+)/set-environment/?", "device_set_environment",
  "/environment/list/?", "environment_list",
  "/bmm/pxe_config/list/?", "pxe_config_list",
  "/bmm/pxe_config/([^/]+)/details/?", "pxe_config_details",
  "/relay/([^/]+)/test/?", "test_two_way_comms",
)

class test_two_way_comms(Handler):
    @relayredirect
    @templeton.handlers.json_response
    def GET(self, relay_name):
        a = api.API(self.db)
        # starts a comm check and return the results
        return { 'success' : a.test_two_way_comms.run(relay_name)}

class power_cycle(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name):
        args, body = templeton.handlers.get_request_parms()
        a = api.API(self.db)
        if 'pxe_config' in body:
            # update the boot config in the db
            img_info = self.db.devices.get_next_image(device_name)
            self.db.devices.set_next_image(device_name,
                    img_info['image'], body.get('boot_config', ''))
            # and the pxe config on disk
            a.set_pxe.run(device_name, body['pxe_config'])
        else:
            a.clear_pxe.run(device_name)
        # start the power cycle and ignore the result
        a.powercycle.start(lambda res : None, device_name)
        return {}

class power_off(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def GET(self, device_name):
        # start the power off and ignore the result
        a = api.API(self.db)
        a.poweroff.start(lambda res : None, device_name)
        return {}

class ping(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def GET(self, device_name):
        a = api.API(self.db)
        # perform a synchronous ping
        return { 'success' : a.ping.run(device_name) }

class clear_pxe(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name):
        a = api.API(self.db)
        a.clear_pxe.run(device_name)
        return {}

class device_log(Handler):
    @templeton.handlers.json_response
    def GET(self, device_name):
        args, _ = templeton.handlers.get_request_parms()
        if 'timeperiod' in args:
            seconds = int(args['timeperiod'][0])
            timeperiod = datetime.timedelta(seconds=seconds)
        else:
            timeperiod = None
        if 'limit' in args:
            limit = int(args['limit'][0])
        else:
            limit = None
        return {'log':self.db.devices.get_logs(device_name,
                timeperiod=timeperiod, limit=limit)}

class device_set_comments(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name):
        args, body = templeton.handlers.get_request_parms()
        self.db.devices.set_comments(device_name, body['comments'])

class device_set_environment(Handler):
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name):
        args, body = templeton.handlers.get_request_parms()
        self.db.devices.set_environment(device_name, body['environment'])

class device_bootconfig(Handler):
    def GET(self, device_name):
        img = self.db.devices.get_next_image(device_name)
        # this is JSON, but we're returning it as a string..
        web.header('Content-Type', 'application/json; charset=utf-8')
        return img['boot_config']

class environment_list(Handler):
    @templeton.handlers.json_response
    def GET(self):
        return { 'environments' : self.db.environments.list() }

class pxe_config_list(Handler):
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        return { 'pxe_configs' : sorted(self.db.pxe_configs.list(
            active_only=('active_only' in args))) }

class pxe_config_details(Handler):
    @templeton.handlers.json_response
    def GET(self, name):
        return { 'details' : self.db.pxe_configs.get(name) }
