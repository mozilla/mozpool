# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Functions common to all handlers."""

import web.webapi
from mozpool import config
from mozpool.db import data

nocontent = NoContent = web.webapi._status_code("204 No Content")

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
        # otherwise, send an access-control header, so that pages in other domains can
        # call this API endpoint without trouble
        fqdns = data.all_imaging_servers()
        origins = [ 'http://%s' % fqdn for fqdn in fqdns ]
        web.header('Access-Control-Allow-Origin', ' '.join(origins))
        return function(self, id, *args)
    return wrapped

