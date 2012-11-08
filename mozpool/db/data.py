# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import sqlalchemy
from sqlalchemy.sql import exists, not_, or_, select
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

def dump_devices(*device_names):
    """
    Dump device data.  This returns a list of dictionaries with keys id, name,
    fqdn, invenetory_id, mac_address, imaging_server, relay_info, and state.
    Zero or more device names should be passed in as positional arguments.  If
    none are given, dumps all device data.
    """
    conn = sql.get_conn()
    devices = model.devices
    img_svrs = model.imaging_servers
    stmt = sqlalchemy.select(
        [devices.c.id, devices.c.name, devices.c.fqdn, devices.c.inventory_id,
         devices.c.mac_address, img_svrs.c.fqdn.label('imaging_server'),
         devices.c.relay_info, devices.c.state],
        from_obj=[devices.join(img_svrs)])
    if device_names:
        id_exprs = []
        for i in device_names:
            id_exprs.append('devices.name=="%s"' % i)
        if len(id_exprs) == 1:
            id_exprs = id_exprs[0]
        else:
            id_exprs = or_(*id_exprs)
        stmt = stmt.where(id_exprs)
    res = conn.execute(stmt)
    return [dict(row) for row in res]

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

    # convert imaging_server to its ID, and add a default state and counters
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    values['state'] = 'new'
    values['state_counters'] = '{}'

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

    # convert imaging_server to its ID, and strip the id
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

# state machine utilities

def get_device_state(device_name):
    """
    Get the state of this device - (state, timeout, counters)
    """
    tbl = model.devices
    res = sql.get_conn().execute(select(
        [tbl.c.state, tbl.c.state_timeout, tbl.c.state_counters],
        tbl.c.name==device_name))
    row = res.fetchone()
    if row is None:
        raise NotFound
    state_counters = row['state_counters']
    if state_counters:
        state_counters = json.loads(state_counters)
    else:
        state_counters = {}
    return row['state'], row['state_timeout'], state_counters

def set_device_state(device_name, state, timeout):
    """
    Set the state of this device, without counters
    """
    sql.get_conn().execute(model.devices.update().
            where(model.devices.c.name==device_name).
            values(state=state, state_timeout=timeout))

def set_device_counters(device_name, counters):
    """
    Set the counters for this device
    """
    sql.get_conn().execute(model.devices.update().
            where(model.devices.c.name==device_name).
            values(state_counters=json.dumps(counters)))

def get_timed_out_devices(imaging_server_id):
    """
    Get a list of all devices whose timeout is in the past, and which belong to
    this imaging server.
    """
    now = datetime.datetime.now()
    res = sql.get_conn().execute(select(
        [model.devices.c.name],
        (model.devices.c.state_timeout < now)
            & (model.devices.c.imaging_server_id == imaging_server_id)))
    timed_out = [ r[0] for r in res.fetchall() ]
    return timed_out

# The rest of the device methods should not have to check for a valid device.
# Handler methods will check before calling.
def device_status(device):
    """
    Get the status of device.
    """
    res = sql.get_conn().execute(select([model.devices.c.state],
                                        model.devices.c.name==device))
    row = res.fetchall()[0]
    return {"state": row['state'].encode('utf-8'),
            "log": logs.device_logs.get(device)}

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

def set_device_config(device, pxe_config_name, config_data):
    """
    Set the config parameters for the /boot/ API for device.
    """
    conn = sql.get_conn()
    res = conn.execute(select([model.pxe_configs.c.id]).
            where(model.pxe_configs.c.name==pxe_config_name))
    pxe_config_id = res.fetchall()[0][0]
    conn.execute(model.devices.update().
                 where(model.devices.c.name==device).
                 values(last_pxe_config_id=pxe_config_id,
                         boot_config=json.dumps(config_data)))
    return config

def device_relay_info(device):
    res = sql.get_conn().execute(select([model.devices.c.relay_info],
                                        model.devices.c.name==device))
    row = res.fetchone()
    if not row:
        raise NotFound
    hostname, bank, relay = row[0].split(":", 2)
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

def list_pxe_configs():
    conn = sql.get_conn()
    res = conn.execute(select([model.pxe_configs.c.name]))
    return {'pxe_configs': [row[0].encode('utf-8') for row in res]}

def pxe_config_details(image):
    conn = sql.get_conn()
    res = conn.execute(select([model.pxe_configs],
                              model.pxe_configs.c.name==image))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return {'details': row_to_dict(row, model.pxe_configs, omit_cols=['id'])}

def get_unassigned_devices():
    conn = sql.get_conn()
    res = conn.execute(select([model.devices.c.name]).where(not_(exists(select([model.requests.c.id]).where(model.requests.c.device_id==model.devices.c.id)))))
    return [row[0] for row in res]

def reserve_device(device_id, assignee, duration):
    conn = sql.get_conn()
    server_id = conn.execute(select([model.imaging_servers.c.id],
                                    model.imaging_servers.c.fqdn==config.get('server', 'fqdn'))).fetchall()[0][0]
    reservation = {'device_id': device_id,
                   'assignee': assignee,
                   'status': 'pending',
                   'expires': datetime.datetime.now() +
                   datetime.timedelta(seconds=duration),
                   'imaging_server_id': server_id}
    try:
        res = conn.execute(model.requests.insert(), reservation)
    except sqlalchemy.exc.IntegrityError:
        return None
    return conn.execute(select([model.requests.c.id]).where(model.requests.c.device_id==device_id)).fetchall()[0][0]

def get_server_for_request(request_id):
    """
    Get the name of the imaging server associated with this device.
    """
    res = sql.get_conn().execute(select([model.imaging_servers.c.fqdn],
                                        from_obj=[model.requests.join(model.imaging_servers)]).where(model.requests.c.id == request_id))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return row[0].encode('utf-8')

def end_request(request_id):
    conn = sql.get_conn()
    conn.execute(model.requests.delete().where(model.requests.c.id==request_id))

def dump_requests(*request_ids):
    conn = sql.get_conn()
    requests = model.requests
    stmt = sqlalchemy.select(
        [requests.c.id, model.devices.c.name.label('device'),
         model.imaging_servers.c.fqdn.label('imaging_server'),
         requests.c.assignee, requests.c.status, requests.c.expires],
        from_obj=[requests.join(model.imaging_servers).join(model.devices)])
    if request_ids:
        id_exprs = []
        for i in request_ids:
            id_exprs.append('requests.id=="%s"' % i)
        if len(id_exprs) == 1:
            id_exprs = id_exprs[0]
        else:
            id_exprs = or_(*id_exprs)
        stmt = stmt.where(id_exprs)
    res = conn.execute(stmt)
    return [dict(row) for row in res]

def renew_request(request_id, duration):
    conn = sql.get_conn()
    conn.execute(model.requests.update(model.requests).values(expires=datetime.datetime.now() + datetime.timedelta(seconds=duration)).where(model.requests.c.id==request_id))

def update_request_status(request_id, old_status, new_status):
    conn = sql.get_conn()
    current_status = conn.execute(select([model.requests.c.status]).where(model.requests.c.id==request_id)).fetchall()[0][0]
    if old_status != current_status:
        raise InvalidStateChange(old_status, new_status, current_status)
    conn.execute(model.requests.update(model.requests).values(status=new_status).where(model.requests.c.id==request_id))
