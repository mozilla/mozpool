# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Functions for testing. Used by the unit tests, but also useful for
manual testing.
"""

import datetime
import os
from sqlalchemy.sql import and_, select
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

def add_hardware_type(hw_type, hw_model):
    res = sql.get_conn().execute(model.hardware_types.insert(), type=hw_type,
                                 model=hw_model)
    return res.lastrowid

def add_device(device, server="server", state="offline",
              mac_address="000000000000",
              log=[], config='{}', relayinfo="",
              last_image_id=None, hardware_type_id=1,
              environment=None):
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
                 last_image_id=last_image_id,
                 hardware_type_id=hardware_type_id,
                 environment=environment)
    inventory_id += 1

def add_pxe_config(name, description="Boot image",
                  contents="BOOT THIS THINGIE WITH THIS CONFIG",
                  id=None, active=True):
    sql.get_conn().execute(model.pxe_configs.insert(), name=name,
                           description=description,
                           contents=contents,
                           id=id,
                           active=active)

def add_image(name, boot_config_keys='[]', can_reuse=False, id=None,
              hidden=False, has_sut_agent=True):
    sql.get_conn().execute(model.images.insert(),
                           id=id,
                           name=name,
                           boot_config_keys=boot_config_keys,
                           can_reuse=can_reuse,
                           hidden=hidden,
                           has_sut_agent=has_sut_agent)

def add_image_pxe_config(image_name, pxe_config_name, hardware_type,
                         hardware_model):
    conn = sql.get_conn()
    image_id = conn.execute(select(
            [model.images.c.id], model.images.c.name==image_name)).fetchone()[0]
    pxe_config_id = conn.execute(select(
            [model.pxe_configs.c.id],
            model.pxe_configs.c.name==pxe_config_name)).fetchone()[0]
    hardware_type_id = conn.execute(select(
            [model.hardware_types.c.id],
            and_(model.hardware_types.c.type==hardware_type,
                 model.hardware_types.c.model==hardware_model))).fetchone()[0]
    if image_id is None or pxe_config_id is None or hardware_type_id is None:
        raise data.NotFound
    conn.execute(model.image_pxe_configs.insert(),
                 image_id=image_id,
                 pxe_config_id=pxe_config_id,
                 hardware_type_id=hardware_type_id)

def add_request(server, assignee="slave", state="new", expires=None,
                device='any', image='b2g', boot_config='{}'):
    if not expires:
        expires = datetime.datetime.now() + datetime.timedelta(hours=1)
    conn = sql.get_conn()
    image_id = conn.execute(select([model.images.c.id],
                                   model.images.c.name==image)).fetchone()[0]
    if image_id is None:
        raise data.NotFound
    server_id = conn.execute(select([model.imaging_servers.c.id],
                                    model.imaging_servers.c.fqdn==server)).fetchone()[0]
    if server_id is None:
        raise data.NotFound
    res = conn.execute(model.requests.insert(),
                       imaging_server_id=server_id,
                       requested_device=device,
                       assignee=assignee,
                       expires=expires,
                       image_id=image_id,
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
