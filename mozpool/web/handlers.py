# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Utilities common to all handlers."""

import json
import time
import threading
import datetime
import web.webapi
from mozpool import config
from mozpool.db import exceptions

nocontent = NoContent = web.webapi._status_code("204 No Content")

class DateTimeJSONEncoder(json.JSONEncoder):
    """Encodes datetime objects as ISO strings."""
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)

def deviceredirect(function):
    """
    Generate a redirect when a request is made for a device that is not managed
    by this instance of the service.  If no redirect is generated, but the
    request is cross-origin, generate an appropriate header in response.
    """
    def wrapped(self, id, *args):
        try:
            server = self.db.devices.get_imaging_server(id)
        except exceptions.NotFound:
            raise web.notfound()
        if server != config.get('server', 'fqdn'):
            raise web.found("http://%s%s" % (server, web.ctx.path))
        # send an appropriate access-control header, if necessary
        origin = web.ctx.environ.get('HTTP_ORIGIN')
        if origin and origin.startswith('http://'):
            origin_hostname = origin[7:]
            fqdns = self.db.imaging_servers.list()
            if origin_hostname not in fqdns:
                raise web.Forbidden
            web.header('Access-Control-Allow-Origin', origin)
        return function(self, id, *args)
    return wrapped


def requestredirect(function):
    """
    Generate a redirect when a request is made for a device that is not
    managed by this instance of the service.
    """
    def wrapped(self, id, *args):
        try:
            server = self.db.requests.get_imaging_server(id)
        except exceptions.NotFound:
            raise web.notfound()
        if server != config.get('server', 'fqdn'):
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

def relayredirect(function):
    """
    Generate a redirect when a request is made for a relay board that is not
    managed by this instance of the service.
    """
    def wrapped(self, id, *args):
        try:
            server = self.db.relay_boards.get_imaging_server(id)
        except exceptions.NotFound:
            raise web.notfound()
        if server != config.get('server', 'fqdn'):
            raise web.found("http://%s%s" % (server, web.ctx.path))
        return function(self, id, *args)
    return wrapped

class Handler(object):
    """
    Parent class for all handler classes in Mozpool.  This makes 'self.db'
    accessible -- it is set in get_app.
    """

    db = None


class InMemCacheMixin(object):
    """
    Mixin for handler classes that want an in-memory cache for their data.
    This is a simple one-variable cache.

    Set CACHE_TTL as a class-level variable, and implement update_cache.
    This class provides cache_get.

    The class variable cache_expires can be used to get the expiration time for HTTP headers, etc.
    """

    CACHE_TTL = 60

    class __metaclass__(type):
        def __new__(meta, classname, bases, classDict):
            cls = type.__new__(meta, classname, bases, classDict)
            cls.cache_data = None
            cls.cache_expires = 0
            cls.cache_lock = threading.Lock()
            return cls

    def update_cache(self):
        raise NotImplementedError

    def cache_get(self):
        cls = self.__class__
        with cls.cache_lock:
            if cls.cache_expires > time.time():
                return cls.cache_data
            cls.cache_data = self.update_cache()
            cls.cache_expires = time.time() + cls.CACHE_TTL
            return cls.cache_data


class ConflictJSON(web.HTTPError):
    """`409 Conflict` error with JSON body."""
    def __init__(self, o):
        status = "409 Conflict"
        body = json.dumps(o, cls=DateTimeJSONEncoder)
        headers = {'Content-Length': len(body),
                   'Content-Type': 'application/json; charset=utf-8'}
        web.HTTPError.__init__(self, status, headers, body)


