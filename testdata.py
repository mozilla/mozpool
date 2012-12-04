#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Put some fake data into a sqlite database. Useful for testing.
"""

# conn is the DB connection

import datetime
import math
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

# max 8 relays each in max 4 banks per server
num_servers = int(math.ceil(options.devices / 32.0))

if num_servers > 1:
    print 'More than the maximum number of devices per server (32) specified.'
    print 'Extra devices will be configured with an unreachable server.'

img_svr_ids = []
fqdns = []

for i in range(0, num_servers):
    if i == 0:
        fqdn = socket.getfqdn()
        if options.port != 80:
            fqdn += ':%d' % options.port
    else:
        fqdn = 'fakeserver%d.local' % i

    fqdns.append(fqdn)
    r = conn.execute(model.imaging_servers.insert(), fqdn=fqdn)
    img_svr_ids.append(r.inserted_primary_key[0])

device_ids = []

for device_id in range(0, options.devices):
    server_id, relay = divmod(device_id, 32)
    bank, relay = [x + 1 for x in divmod(relay, 8)]
    r = conn.execute(model.devices.insert(),
                     name='device%d' % (device_id + 1),
                     fqdn='device%d.fqdn' % (device_id + 1),
                     inventory_id=1111 * (device_id + 1),
                     state='free',
                     environment='odd' if (device_id % 2) else 'even',
                     state_counters='{}',
                     mac_address='%012x' % device_id,
                     imaging_server_id=img_svr_ids[server_id],
                     relay_info='%s:bank%d:relay%d' % (fqdns[server_id], bank,
                                                       relay),
                     boot_config='')
    device_ids.append(r.inserted_primary_key[0])

for request_id in range(1, options.requests+1):
    conn.execute(model.requests.insert(),
                 requested_device='any',
                 assignee='slave%d' % request_id,
                 state='new',
                 state_counters='{}',
                 imaging_server_id=img_svr_ids[0],
                 expires=datetime.datetime.now() +
                         datetime.timedelta(seconds=12*60*60))

conn.execute(model.pxe_configs.insert(),
        name='image1',
        description='test img',
        contents='some config',
        active=True)
