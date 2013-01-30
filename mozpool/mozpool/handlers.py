# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import templeton
import web

import mozpool.mozpool
from mozpool import config
from mozpool.db import data, logs
from mozpool.web import handlers as mozpool_handlers

urls = (
    "/device/list/?", "device_list",
    "/device/([^/]+)/request/?", "device_request",

    "/request/list/?", "request_list",
    "/request/([^/]+)/details/?", "request_details",
    "/request/([^/]+)/status/?", "request_status",
    "/request/([^/]+)/log/?", "request_log",
    "/request/([^/]+)/renew/?", "request_renew",
    "/request/([^/]+)/return/?", "request_return",

    "/image/list/?", "image_list",
)

class ConflictJSON(web.HTTPError):
    """`409 Conflict` error with JSON body."""
    def __init__(self, o):
        status = "409 Conflict"
        body = json.dumps(o)
        headers = {'Content-Length': len(body),
                   'Content-Type': 'application/json; charset=utf-8'}
        web.HTTPError.__init__(self, status, headers, body)


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
        try:
            assignee = body['assignee']
            duration = int(body['duration'])
            image_name = body['image']
            environment = body.get('environment', 'any')
        except (KeyError, ValueError):
            raise web.badrequest()

        images = data.dump_images(image_name)
        if not images:
            raise web.badrequest()

        boot_config = {}
        for k in images[0]['boot_config_keys']:
            try:
                boot_config[k] = body[k]
            except KeyError:
                raise web.badrequest()

        request_id = data.create_request(device_name, environment, assignee,
                                         duration, images[0]['id'], boot_config)
        mozpool.mozpool.driver.handle_event(request_id, 'find_device', None)
        response_data = {'request': data.request_config(request_id)}
        if data.request_status(request_id)['state'] == 'closed':
            raise ConflictJSON(response_data)
        return response_data

class device_list:
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        return data.list_devices(detail='details' in args)

class request_list:
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        include_closed = args.get('include_closed', False)
        return dict(requests=data.dump_requests(include_closed=include_closed))

class request_details:
    @templeton.handlers.json_response
    def GET(self, request_id):
        try:
            return data.request_config(int(request_id))
        except ValueError:
            raise web.badrequest()
        except data.NotFound:
            raise web.notfound()

class request_status:
    @templeton.handlers.json_response
    def GET(self, request_id):
        try:
            return data.request_status(request_id)
        except IndexError:
            raise web.notfound()

class request_log:
    @templeton.handlers.json_response
    def GET(self, request_id):
        return {'log': logs.request_logs.get(request_id)}

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
        mozpool.mozpool.driver.handle_event(request_id, 'close', None)
        raise mozpool_handlers.nocontent()

class image_list:
    @templeton.handlers.json_response
    def GET(self):
        return {'images': data.dump_images()}
