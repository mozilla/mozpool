# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import templeton
import web

import mozpool.mozpool
from mozpool import config
from mozpool.db import exceptions
from mozpool.web.handlers import Handler, requestredirect, nocontent, ConflictJSON

urls = (
    "/device/list/?", "device_list",
    "/device/([^/]+)/request/?", "device_request",

    "/request/list/?", "request_list",
    "/request/([^/]+)/details/?", "request_details",
    "/request/([^/]+)/status/?", "request_status",
    "/request/([^/]+)/log/?", "request_log",
    "/request/([^/]+)/renew/?", "request_renew",
    "/request/([^/]+)/return/?", "request_return",
    "/request/([^/]+)/event/([^/]+)/?", "request_event",

    "/image/list/?", "image_list",
)

class device_list(Handler):
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        return {'devices': self.db.devices.list(detail='details' in args)}

class device_request(Handler):
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

        try:
            image = self.db.images.get(image_name)
        except exceptions.NotFound:
            raise web.notfound()

        boot_config = {}
        for k in image['boot_config_keys']:
            try:
                boot_config[k] = body[k]
            except KeyError:
                raise web.badrequest()

        request_id = self.db.requests.add(device_name, environment, assignee,
                duration, image['id'], boot_config)
        mozpool.mozpool.driver.handle_event(request_id, 'find_device', None)
        info = self.db.requests.get_info(request_id)
        info['url'] = "http://%s/api/request/%d/" % ((config.get('server', 'fqdn'), request_id))
        response_data = {'request': info}
        if self.db.requests.get_machine_state(request_id) == 'closed':
            raise ConflictJSON(response_data)
        return response_data

class request_list(Handler):
    @templeton.handlers.json_response
    def GET(self):
        args, _ = templeton.handlers.get_request_parms()
        include_closed = args.get('include_closed', False)
        return dict(requests=self.db.requests.list(include_closed=include_closed))

class request_details(Handler):
    @templeton.handlers.json_response
    def GET(self, request_id):
        try:
            request_id = int(request_id)
            info = self.db.requests.get_info(request_id)
            info['url'] = "http://%s/api/request/%d/" % ((config.get('server', 'fqdn'), request_id))
            return info
        except ValueError:
            raise web.badrequest()
        except exceptions.NotFound:
            raise web.notfound()

class request_status(Handler):
    @templeton.handlers.json_response
    def GET(self, request_id):
        state = self.db.requests.get_machine_state(request_id)
        logs = self.db.requests.get_logs(request_id, limit=100)
        return {'state': state, 'log': logs}

class request_log(Handler):
    @templeton.handlers.json_response
    def GET(self, request_id):
        return {'log':self.db.requests.get_logs(request_id)}

class request_renew(Handler):
    @requestredirect
    def POST(self, request_id):
        _, body = templeton.handlers.get_request_parms()
        try:
            new_duration = int(body["duration"])
            request_id = int(request_id)
        except (KeyError, ValueError):
            raise web.badrequest()
        self.db.requests.renew(request_id, new_duration)
        raise nocontent()

class request_return(Handler):
    @requestredirect
    def POST(self, request_id):
        mozpool.mozpool.driver.handle_event(int(request_id), 'close', None)
        raise nocontent()

class request_event(Handler):
    @requestredirect
    @templeton.handlers.json_response
    def POST(self, request_id, event):
        args, body = templeton.handlers.get_request_parms()
        mozpool.mozpool.driver.handle_event(int(request_id), event, body)
        return {}

    @requestredirect
    @templeton.handlers.json_response
    def GET(self, request_id, event):
        mozpool.mozpool.driver.handle_event(int(request_id), event, {})
        return {}

class image_list(Handler):
    @templeton.handlers.json_response
    def GET(self):
        return {'images': self.db.images.list()}
