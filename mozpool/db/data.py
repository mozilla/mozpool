# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import sqlalchemy
from sqlalchemy.sql import exists, not_, select
from itertools import izip_longest
from mozpool.db import logs, model, sql
from mozpool import config

class NotFound(Exception):
    pass

class InvalidStateChange(Exception):
    
    def __init__(self, old_state, new_state, current_state):
        self.old_state = old_state
        self.new_state = new_state
        self.current_state = current_state
        Exception.__init__(self, 'invalid state change request from "%s" '
                           'to "%s" in current state "%s"' %
                           (self.old_state, self.new_state, self.current_state))

def row_to_dict(row, table, omit_cols=[]):
    """
    Convert a result row to a dict using the schema from table.
    If omit_cols is specified, omit columns whose names are present
    in that list.
    """
    result = {}
    for col in table.c:
        if col.name in omit_cols:
            continue
        coldata = row[col]
        if isinstance(coldata, unicode):
            coldata = coldata.encode('utf-8')
        result[col.name] = coldata
    return result

def list_devices():
    """
    Get the list of all devices known to the system.
    Returns a dict whose 'devices' entry is the list of devices.
    """
    conn = sql.get_conn()
    res = conn.execute(select([model.devices.c.name]))
    return {'devices': [row[0].encode('utf-8') for row in res]}

def dump_devices():
    """
    Dump all devices.  This returns a list of dictionaries with keys id, name,
    fqdn, invenetory_id, mac_address, imaging_server, relay_info, and status.
    """
    conn = sql.get_conn()
    devices = model.devices
    img_svrs = model.imaging_servers
    res = conn.execute(sqlalchemy.select(
        [ devices.c.id, devices.c.name, devices.c.fqdn, devices.c.inventory_id, devices.c.mac_address,
          img_svrs.c.fqdn.label('imaging_server'), devices.c.relay_info, devices.c.status ],
        from_obj=[devices.join(img_svrs)]))
    return [ dict(row) for row in res ]

def find_imaging_server_id(name):
    """Given an imaging server name, either return the existing ID, or a new ID."""
    conn = sql.get_conn()

    # try inserting, ignoring failures (most likely due to duplicate row)
    try:
        conn.execute(model.imaging_servers.insert(),
            fqdn=name)
    except sqlalchemy.exc.SQLAlchemyError:
        pass # probably already exists

    res = conn.execute(sqlalchemy.select([ model.imaging_servers.c.id ],
                        whereclause=(model.imaging_servers.c.fqdn==name)))
    return res.fetchall()[0].id

def insert_device(values):
    """Insert a new device into the DB.  VALUES should be in the dictionary
    format used for inventorysync - see inventorysync.py"""
    values = values.copy()

    # convert imaging_server to its ID, and add a default status
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    values['status'] = 'new'

    sql.get_conn().execute(model.devices.insert(), [ values ])

def delete_device(id):
    """Delete the device with the given ID"""
    conn = sql.get_conn()
    # foreign keys don't automatically delete log entries, so do it manually.
    # This table is partitioned, so there's no need to later optimize these
    # deletes - they'll get flushed when their parititon is dropped.
    logs.device_logs.delete_all(id)
    conn.execute(model.devices.delete(), whereclause=(model.devices.c.id==id))

def update_device(id, values):
    """Update an existing device with id ID into the DB.  VALUES should be in
    the dictionary format used for inventorysync - see inventorysync.py"""
    values = values.copy()

    # convert imaging_server to its ID, and add a default status
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    if 'id' in values:
        values.pop('id')

    sql.get_conn().execute(model.devices.update(whereclause=(model.devices.c.id==id)), **values)

def get_server_for_device(device):
    """
    Get the name of the imaging server associated with this device.
    """
    res = sql.get_conn().execute(select([model.imaging_servers.c.fqdn],
                                        from_obj=[model.devices.join(model.imaging_servers)]).where(model.devices.c.name == device))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return row[0].encode('utf-8')

# The rest of the device methods should not have to check for a valid device.
# Handler methods will check before calling.
def device_status(device):
    """
    Get the status of device.
    """
    res = sql.get_conn().execute(select([model.devices.c.status],
                                        model.devices.c.name==device))
    row = res.fetchall()[0]
    return {"status": row['status'].encode('utf-8'),
            "log": logs.device_logs.get(device)}

def set_device_status(device, status):
    """
    Set the status of device to status.
    """
    sql.get_conn().execute(model.devices.update().
                           where(model.devices.c.name==device).
                           values(status=status))
    return status

def device_config(device):
    """
    Get the config parameters passed to the /boot/ API for device.
    """
    res = sql.get_conn().execute(select([model.devices.c.boot_config],
                                        model.devices.c.name==device))
    row = res.fetchone()
    config_data = {}
    if row:
        config_data = json.loads(row['boot_config'].encode('utf-8'))
    return {'config': config_data}

def set_device_config(device, config_data):
    """
    Set the config parameters for the /boot/ API for device.
    """
    sql.get_conn().execute(model.devices.update().
                           where(model.devices.c.name==device).
                           values(boot_config=json.dumps(config_data)))
    return config

def device_relay_info(device):
    res = sql.get_conn().execute(select([model.devices.c.relay_info],
                                        model.devices.c.name==device))
    info = res.fetchone()[0]
    hostname, bank, relay = info.split(":", 2)
    assert bank.startswith("bank") and relay.startswith("relay")
    return hostname, int(bank[4:]), int(relay[5:])

def mac_with_dashes(mac):
    """
    Reformat a 12-digit MAC address to contain
    a dash between each 2 characters.
    """
    # From the itertools docs.
    return "-".join("%s%s" % i for i in izip_longest(fillvalue=None, *[iter(mac)]*2))

def device_mac_address(device):
    """
    Get the mac address of device.
    """
    res = sql.get_conn().execute(select([model.devices.c.mac_address],
                                        model.devices.c.name==device))
    row = res.fetchone()
    return row['mac_address'].encode('utf-8')

def list_bootimages():
    conn = sql.get_conn()
    res = conn.execute(select([model.images.c.name]))
    return {'bootimages': [row[0].encode('utf-8') for row in res]}

def bootimage_details(image):
    conn = sql.get_conn()
    res = conn.execute(select([model.images],
                              model.images.c.name==image))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return {'details': row_to_dict(row, model.images, omit_cols=['id'])}

def get_unassigned_devices():
    conn = sql.get_conn()
    res = conn.execute(select([model.devices.c.name]).where(not_(exists(select([model.requests.c.id]).where(model.requests.c.device_id==model.devices.c.id)))))
    return {'devices': [row[0].encode('utf-8') for row in res]}

def reserve_device(device, assignee, duration):
    conn = sql.get_conn()
    try:
        device_id = conn.execute(select([model.devices.c.id]).where(model.devices.c.name==device)).fetchall()[0][0]
    except IndexError:
        raise NotFound
    reservation = {'device_id': device_id,
                   'assignee': assignee,
                   'status': 'pending',
                   'expires': datetime.datetime.now() +
                   datetime.timedelta(seconds=duration)}
    try:
        res = conn.execute(model.requests.insert(), reservation)
    except sqlalchemy.exc.IntegrityError:
        return None
    return conn.execute(select([model.requests.c.id]).where(model.requests.c.device_id==device_id)).fetchall()[0][0]

def end_request(request_id):
    conn = sql.get_conn()
    conn.execute(model.requests.delete().where(model.requests.c.id==request_id))

def dump_requests():
    conn = sql.get_conn()
    return [row_to_dict(x, model.requests) for x in
            conn.execute(select([model.requests]))]

def update_request_duration(request_id, duration):
    conn = sql.get_conn()
    conn.execute(model.requests.update(model.requests).values(expires=datetime.datetime.now() + datetime.timedelta(seconds=duration)).where(model.requests.c.id==request_id))

def update_request_status(request_id, old_status, new_status):
    conn = sql.get_conn()
    current_status = conn.execute(select([model.requests.c.status]).where(model.requests.c.id==request_id)).fetchall()[0][0]
    if old_status != current_status:
        raise InvalidStateChange(old_status, new_status, current_status)
    conn.execute(model.requests.update(model.requests).values(status=new_status).where(model.requests.c.id==request_id))
