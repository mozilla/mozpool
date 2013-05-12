# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from  mozpool import config
from . import pool, inventorysync, imaging_servers, requests, devices
from . import device_requests, pxe_configs, environments, images, relay_boards

class DB(object):

    def __init__(self, db_url):
        # make the pool and make its 'execute' method easy to find
        self.pool = pool.DBPool(db_url)
        self.execute = self.pool.execute

        # instantiate each Methods class.  This provides a nice scoped facade
        # where simply-named methods are scoped by topic, e.g., self.images.get
        # and self.environments.list.
        self.requests = requests.Methods(self)
        self.devices = devices.Methods(self)
        self.device_requests = device_requests.Methods(self)
        self.imaging_servers = imaging_servers.Methods(self)
        self.images = images.Methods(self)
        self.environments = environments.Methods(self)
        self.pxe_configs = pxe_configs.Methods(self)
        self.inventorysync = inventorysync.Methods(self)
        self.relay_boards = relay_boards.Methods(self)

def setup(db_url=None):
    if not db_url:
        db_url = config.get('database', 'engine')
    return DB(db_url)
