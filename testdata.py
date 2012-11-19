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
parser.add_option('-d', '--devices', dest='devices', action='store', type='int',
                  default=1)
parser.add_option('-r', '--requests', dest='requests', action='store',
                  type='int', default=0)
parser.add_option('-p', '--port', dest='port', action='store', type='int',
                  default=80)
(options, args) = parser.parse_args(args)

fqdn_with_port = fqdn = socket.getfqdn()
if options.port != 80:
    fqdn_with_port += ':%d' % options.port

r = conn.execute(model.imaging_servers.insert(), fqdn=fqdn_with_port)
img_svr_id = r.inserted_primary_key[0]

for device_id in range(1, options.devices+1):
    conn.execute(model.devices.insert(),
                 name='device%d' % device_id,
                 fqdn='device%d.fqdn' % device_id,
                 inventory_id=1111 * device_id,
                 state='ready',
                 state_counters='{}',
                 mac_address='%012x' % device_id,
                 imaging_server_id=img_svr_id,
                 relay_info='%s:bank1:relay%d' % (fqdn, device_id),
                 boot_config='')

for request_id in range(1, options.requests+1):
    conn.execute(model.requests.insert(),
                 device_id=request_id,
                 requested_device='any',
                 assignee='slave%d' % request_id,
                 state='new',
                 state_counters='{}',
                 imaging_server_id=img_svr_id,
                 expires=datetime.datetime.now() +
                         datetime.timedelta(seconds=12*60*60))

conn.execute(model.pxe_configs.insert(),
        name='image1',
        description='test img',
        contents='some config',
        active=True)
