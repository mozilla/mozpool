# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import web
import templeton
from mozpool.db import data, logs
from mozpool.web.handlers import deviceredirect
from mozpool.bmm import api

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  "/device/([^/]+)/power-cycle/?", "power_cycle",
  "/device/([^/]+)/power-off/?", "power_off",
  "/device/([^/]+)/ping/?", "ping",
  "/device/([^/]+)/clear-pxe/?", "clear_pxe",
  "/device/([^/]+)/log/?", "log",
  "/device/([^/]+)/bootconfig/?", "device_bootconfig",
  "/device/([^/]+)/set-comments/?", "device_set_comments",
  "/device/([^/]+)/set-environment/?", "device_set_environment",
  "/environment/list/?", "environment_list",
  "/bmm/pxe_config/list/?", "pxe_config_list",
  "/bmm/pxe_config/([^/]+)/details/?", "pxe_config_details",
)

class power_cycle:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name):
        args, body = templeton.handlers.get_request_parms()
        if 'pxe_config' in body:
            api.set_pxe(device_name, body['pxe_config'],
                    body.get('boot_config', ''))
        else:
            api.clear_pxe(device_name)
        # start the power cycle and ignore the result
        api.start_powercycle(device_name, lambda *args : None)
        return {}

class power_off:
    @deviceredirect
    @templeton.handlers.json_response
    def GET(self, device_name):
        # start the power off and ignore the result
        api.start_poweroff(device_name, lambda *args : None)
        return {}

class ping:
    @deviceredirect
    @templeton.handlers.json_response
    def GET(self, device_name):
        return { 'success' : api.ping(device_name) }

class clear_pxe:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, device_name):
        api.clear_pxe(device_name)
        return {}

class log:
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
        return {'log':logs.device_logs.get(device_name,
                timeperiod=timeperiod, limit=limit)}

class environment_list:
    @templeton.handlers.json_response
    def GET(self):
        return data.list_environments()

class pxe_config_list:
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        if 'active_only' in args:
            return data.list_pxe_configs(active_only=True)
        else:
            return data.list_pxe_configs()

class pxe_config_details:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.pxe_config_details(id)

class device_set_comments:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, id):
        args, body = templeton.handlers.get_request_parms()
        data.set_device_comments(id, body['comments'])

class device_set_environment:
    @deviceredirect
    @templeton.handlers.json_response
    def POST(self, id):
        args, body = templeton.handlers.get_request_parms()
        data.set_device_environment(id, body['environment'])

class device_bootconfig:
    def GET(self, id):
        try:
            dev_cfg = data.device_config(id)
            web.header('Content-Type', 'application/json; charset=utf-8')
            return dev_cfg['boot_config']
        except KeyError:
            raise web.notfound()
