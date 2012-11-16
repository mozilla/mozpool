# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import random
import templeton
import web

import mozpool.mozpool
from mozpool import config
from mozpool.db import data
from mozpool.web import handlers as mozpool_handlers

urls = (
    "/device/list/?", "device_list",
    "/device/([^/]+)/status/?", "device_status",
    "/device/([^/]+)/request/?", "device_request",

    "/request/list/?", "request_list",
    "/request/([^/]+)/details/?", "request_details",
    "/request/([^/]+)/renew/?", "request_renew",
    "/request/([^/]+)/return/?", "request_return",
)

def requestredirect(function):
    """
    Generate a redirect when a request is made for a device that is not
    managed by this instance of the service.
    """
    def wrapped(self, id, *args):
        try:
            server = data.get_server_for_request(id)
        except data.NotFound:
            raise web.notfound()
        if server != config.get('server', 'fqdn'):
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

class device_request:
    @templeton.handlers.json_response
    def POST(self, device_name):
        args, body = templeton.handlers.get_request_parms()
        boot_config = body.get('boot_config', '{}')
        try:
            assignee = body['assignee']
            duration = int(body['duration'])
        except (KeyError, ValueError):
            raise web.badrequest()
        request_id = data.create_request(device_name, assignee, duration,
                                         boot_config)
        mozpool.mozpool.driver.handle_event(request_id, 'find_device', None)
        request_url = 'http://%s/api/request/%d/' % (config.get('server',
                                                                'fqdn'),
                                                     request_id)
        return {'request': data.dump_requests(request_id)[0],
                'request_url': request_url}

class device_list:
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        if 'details' in args:
            return dict(devices=data.dump_devices())
        else:
            return data.list_devices()

class device_status:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.device_status(id)

class request_list:
    @templeton.handlers.json_response
    def GET(self):
        return data.dump_requests()

class request_details:
    @templeton.handlers.json_response
    def GET(self, request_id):
        try:
            return data.dump_requests(request_id)[0]
        except IndexError:
            raise web.notfound()

class request_renew:
    @requestredirect
    def POST(self, request_id):
        _, body = templeton.handlers.get_request_parms()
        try:
            new_duration = int(body["duration"])
        except (KeyError, ValueError):
            raise web.badrequest()
        data.renew_request(request_id, new_duration)
        raise mozpool_handlers.nocontent()

class request_return:
    @requestredirect
    def POST(self, request_id):
        data.end_request(request_id)
        raise mozpool_handlers.nocontent()
