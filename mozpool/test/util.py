# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Functions for testing. Used by the unit tests, but also useful for
manual testing.
"""

import datetime
import os
from sqlalchemy.sql import select
from mozpool.db import model
from mozpool.db import data, sql

inventory_id = 1

def setup_db(dbfile):
    # blow away the db file so we know we're starting fresh
    if os.path.exists(dbfile):
        os.unlink(dbfile)
    conn = sql.get_conn()
    model.metadata.create_all(sql.engine)

    # clean out the db
    conn.execute(model.imaging_servers.delete())
    conn.execute(model.devices.delete())
    conn.execute(model.pxe_configs.delete())

    # reset the local "fake" stuff too
    global inventory_id
    inventory_id = 1

def add_server(hostname):
    """
    Configure data for a server running at |hostname|.
    """
    sql.get_conn().execute(model.imaging_servers.insert(), fqdn=hostname)

def add_device(device, server="server", state="offline",
              mac_address="000000000000",
              log=[], config='{}', relayinfo="",
              last_pxe_config_id=None):
    global inventory_id
    conn = sql.get_conn()
    id = conn.execute(select([model.imaging_servers.c.id],
                              model.imaging_servers.c.fqdn==server)).fetchone()[0]
    if id is None:
        raise data.NotFound
    conn.execute(model.devices.insert(),
                 name=device,
                 fqdn=device, #XXX
                 inventory_id=inventory_id,
                 state=state,
                 state_counters='{}',
                 mac_address=mac_address,
                 imaging_server_id=id,
                 relay_info=relayinfo,
                 boot_config=config,
                 last_pxe_config_id=last_pxe_config_id)
    inventory_id += 1

def add_pxe_config(name, description="Boot image",
                  contents="BOOT THIS THINGIE WITH THIS CONFIG",
                  id=None, active=True):
    sql.get_conn().execute(model.pxe_configs.insert(), name=name,
                           description=description,
                           contents=contents,
                           id=id,
                           active=active)

def add_request(server, assignee="slave", state="new", expires=None,
                device='any', boot_config='{}'):
    if not expires:
        expires = datetime.datetime.now() + datetime.timedelta(hours=1)
    conn = sql.get_conn()
    server_id = conn.execute(select([model.imaging_servers.c.id],
                                    model.imaging_servers.c.fqdn==server)).fetchone()[0]
    if server_id is None:
        raise data.NotFound
    res = conn.execute(model.requests.insert(),
                       imaging_server_id=server_id,
                       requested_device=device,
                       assignee=assignee,
                       expires=expires,
                       boot_config=boot_config,
                       state=state,
                       state_counters='{}')
    request_id = res.lastrowid
    if device and state != 'closed':
        device_id = conn.execute(select(
                [model.devices.c.id],
                model.devices.c.name==device)).fetchone()[0]
        conn.execute(model.device_requests.insert(),
                     request_id=request_id,
                     device_id=device_id)
