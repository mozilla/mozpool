#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Put some fake data into a sqlite database. Useful for testing.
"""

# conn is the DB connection

import datetime
import socket
from mozpool.db import model
from optparse import OptionParser

parser = OptionParser()
parser.add_option('-b', '--boards', dest='boards', action='store', type='int',
                  default=1)
parser.add_option('-r', '--requests', dest='requests', action='store',
                  type='int', default=0)
(options, args) = parser.parse_args(args)

fqdn = socket.getfqdn()
r = conn.execute(model.imaging_servers.insert(), fqdn=fqdn)
img_svr_id = r.inserted_primary_key[0]

for board_id in range(1, options.boards+1):
    conn.execute(model.boards.insert(),
                 name='board%d' % board_id,
                 fqdn='board%d.fqdn' % board_id,
                 inventory_id=1111 * board_id,
                 status='new',
                 mac_address='%012x' % board_id,
                 imaging_server_id=img_svr_id,
                 relay_info='relay%d' % board_id,
                 boot_config=None)

for request_id in range(1, options.requests+1):
    conn.execute(model.requests.insert(),
                 board_id=request_id,
                 assignee='slave%d' % request_id,
                 status='inuse',
                 expires=datetime.datetime.now() +
                         datetime.timedelta(seconds=12*60*60))

conn.execute(model.images.insert(),
        name='image1',
        version=1,
        description='test img',
        pxe_config_filename='foo/bar')
