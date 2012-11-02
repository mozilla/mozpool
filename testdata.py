#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Put some fake data into a sqlite database. Useful for testing.
"""

# conn is the DB connection

import socket
from mozpool.db import model

fqdn=socket.getfqdn()
r = conn.execute(model.imaging_servers.insert(), fqdn=fqdn)
img_svr_id = r.inserted_primary_key[0]

conn.execute(model.boards.insert(),
        name='board1',
        fqdn='board1.fqdn',
        inventory_id=1111,
        status='new',
        mac_address='aabbccddeeff',
        imaging_server_id=img_svr_id,
        relay_info='a:b:c',
        boot_config=None)

conn.execute(model.images.insert(),
        name='image1',
        version=1,
        description='test img',
        pxe_config_filename='foo/bar')
