#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import argparse
import requests
from mozpool.db import setup
from mozpool import config

# systems are represented as a dict with keys:
#  - id (only for dicts from the database)
#  - name
#  - fqdn
#  - inventory_id
#  - mac_address (from nic.0.mac_address.0)
#  - imaging_server (from system.imaging_server.0)
#  - relay_info (from system.relay.0)
#  - hardware_type (default value used for now)
#  - hardware_model (default value used for now)

_servermodel_cache = {}
def get_servermodel(url, username, password, pk):
    """
    Look up a server model by its primary key, as available in the bulk view
    used by get_devices.  The result is a dictionary with keys 'model' and
    'vendor'.
    """
    if pk not in _servermodel_cache:
        path = '/en-US/core/api/v1_core/servermodel/%d/' % pk
        r = requests.get(url + path, auth=(username, password))
        if r.status_code != requests.codes.ok:
            raise RuntimeError('got status code %s from inventory' % r.status_code)
        _servermodel_cache[pk] = r.json()
    return _servermodel_cache[pk]


_systemstatus_cache = {}
def get_systemstatus(url, username, password, pk):
    """
    Look up a system status by its primary key, as available in the bulk view
    used by get_devices.  The result is the string status.
    """
    if pk not in _systemstatus_cache:
        path = '/en-US/core/api/v1_core/systemstatus/%d/' % pk
        r = requests.get(url + path, auth=(username, password))
        if r.status_code != requests.codes.ok:
            raise RuntimeError('got status code %s from inventory' % r.status_code)
        _systemstatus_cache[pk] = r.json()['status']
    return _systemstatus_cache[pk]


def get_devices(url, filter, username, password, ignore_devices_on_servers_re=None, verbose=False):
    """
    Return a list of hosts from inventory.  FILTER is an inventory-style filter
    for the desired hosts; for a regular expression prefix it with '/'.  Any
    hosts without 'system.relay.0' or the other required inventory keys are
    ignored.  Any hosts without an sreg are ignored.  Any hosts with imaging
    servers matching ignore_devices_on_servers_re are ignored.
    """
    # bulk_export can't paginate, unfortunately
    path = '/en-US/bulk_action/export/?q=' + filter
    rv = []
    r = requests.get(url + path, auth=(username, password))
    if r.status_code != requests.codes.ok:
        raise RuntimeError('got status code %s from inventory' % r.status_code)

    required_keys = 'system.relay.0', 'system.imaging_server.0'
    for hostname, o in r.json()['systems'].iteritems():
        if get_systemstatus(url, username, password, o['system_status']) == "decommissioned":
            if verbose: print hostname, 'SKIPPED - decommissioned'
            continue

        kv = dict([ (k, vv['value']) for k, vv in o['keyvalue_set'].iteritems() ])
        missing = [ k for k in required_keys if k not in kv ]
        if missing:
            if verbose: print hostname, 'SKIPPED - missing k/v value(s)', ' '.join(missing)
            continue

        name = hostname.split('.', 1)[0]

        try:
            mac_address = o['staticreg_set']['nic0']['hwadapter_set']['hw0']['mac']
        except KeyError:
            if verbose: print hostname, 'SKIPPED - no MAC address (looking for SREG "nic0" with adapter "hw0")'
            continue
        mac_address = mac_address.replace(':', '').lower()

        if ignore_devices_on_servers_re and \
           re.match(ignore_devices_on_servers_re, kv['system.imaging_server.0']):
            if verbose: print hostname, 'SKIPPED - ignored imaging server'
            continue

        # look up the server_model
        servermodel = get_servermodel(url, username, password, o['server_model'])
        type, model = servermodel['vendor'], servermodel['model']
        rv.append(dict(
            name=name,
            fqdn=hostname,
            inventory_id=o['pk'],
            mac_address=mac_address,
            imaging_server=kv['system.imaging_server.0'],
            relay_info=kv['system.relay.0'],
            hardware_type=type,
            hardware_model=model))

        if verbose: print hostname, 'downloaded.'

    return rv

def merge_devices(from_db, from_inv):
    """
    Merge a list of hosts in the DB with those in inventory.  This yields a
    list of instructions of the form ('insert', dict), ('delete', id, dict), or
    ('update', id, dict).
    """

    # first, key everything by inventory ID
    from_db = dict([ (r['inventory_id'], r) for r in from_db ])
    from_inv = dict([ (r['inventory_id'], r) for r in from_inv ])

    # get the insert and deletes out of the way
    for invid in set(from_db) - set(from_inv):
        yield ('delete', from_db[invid]['id'], from_db[invid])
    for invid in set(from_inv) - set(from_db):
        yield ('insert', from_inv[invid])

    # now figure out any updates that are required
    for invid in set(from_inv) & set(from_db):
        db_row = from_db[invid].copy()
        id = db_row.pop('id')
        inv_row = from_inv[invid]
        if db_row != inv_row:
            yield ('update', id, inv_row)

def get_relay_boards(from_inv):
    """
    Returns a list of dictionaries containing relay_boards derived from a
    list of device retrieved from inventory.  Since we make the assumtion
    each unique relay board can only have one imaging_system assosiated to it,
    we check for this and raise an AssertionError otherwise.
    """
    relay_list = []
    test_dict = {}
    for device in from_inv:
        fqdn = device['relay_info'].split(':', 1)[0]
        name = fqdn.split('.', 1)[0]
        imaging_server = device['imaging_server']
        if not fqdn in test_dict:
            test_dict[fqdn] = imaging_server
            relay_list.append(dict(name=name,fqdn=fqdn,imaging_server=imaging_server))
        elif test_dict[fqdn] != imaging_server:
            raise RuntimeError("relay '%s' is associated with multiple imaging servers (%r)" % (fqdn, [imaging_server, test_dict[fqdn]]))
    return relay_list

def merge_relay_boards(relay_boards_from_db, relay_boards_from_inv):
    """
    Merge a list of relay_boards in the DB with those in from inventory.  This yields a
    list of instructions of the form ('insert', dict), ('delete', id, dict), or
    ('update', id, dict).
    """

    # first, key everything by fqdn
    relay_boards_from_db = dict([ (r['fqdn'], r) for r in relay_boards_from_db ])
    relay_boards_from_inv = dict([ (r['fqdn'], r) for r in relay_boards_from_inv ])

    # get the insert and deletes out of the way
    for row in set(relay_boards_from_db) - set(relay_boards_from_inv):
        yield ('delete', relay_boards_from_db[row]['id'], relay_boards_from_db[row])
    for row in set(relay_boards_from_inv) - set(relay_boards_from_db):
        yield ('insert', relay_boards_from_inv[row])

    # now figure out any updates that are required
    for row in set(relay_boards_from_inv) & set(relay_boards_from_db):
        db_row = relay_boards_from_db[row].copy()
        id = db_row.pop('id')
        relay_boards_inv_row = relay_boards_from_inv[row]
        if db_row != relay_boards_inv_row:
            yield ('update', id, relay_boards_inv_row)

def sync(db, verbose=False, ship_it=False):
    ignore_devices_on_servers_re = None
    if config.has_option('inventory', 'ignore_devices_on_servers_re'):
        ignore_devices_on_servers_re = config.get('inventory', 'ignore_devices_on_servers_re')
    from_inv = get_devices(
            config.get('inventory', 'url'),
            config.get('inventory', 'filter'),
            config.get('inventory', 'username'),
            config.get('inventory', 'password'),
            ignore_devices_on_servers_re,
            verbose=verbose)
    # dump the db second, since otherwise the mysql server can go away while
    # get_devices is still running, which is no fun
    from_db = db.inventorysync.dump_devices()

    ## get a list of relay_boards derived from the inventory dump
    relay_boards_from_inv = get_relay_boards(from_inv)
    ## get existing relay_board list from DB
    relay_boards_from_db = db.inventorysync.dump_relays()

    # get the list of changes that need to be made
    tasks = list(merge_devices(from_db, from_inv))

    # If there are too many changes, bail out and await human interaction.
    # "Too many" means more than 5 and more than a tenth of the larger of the
    # set of devices currently in inventory and the set in the DB.  This is a
    # failsafe to keep the inventory sync from unexpectedly erasing all
    # devices.
    if len(tasks) > max(5, len(from_db) / 10, len(from_inv) / 10) and not ship_it:
        raise RuntimeError("%d changes: pass --ship-it to make these changes" % len(tasks))

    # start merging devices
    for task in tasks:
        if task[0] == 'insert':
            if verbose: print "insert device", task[1]['fqdn']
            db.inventorysync.insert_device(task[1])
        elif task[0] == 'delete':
            if verbose: print "delete device", task[2]
            db.inventorysync.delete_device(task[1])
        elif task[0] == 'update':
            if verbose: print "update device", task[2]
            db.inventorysync.update_device(task[1], task[2])
        else:
            raise RuntimeError('%s is not a task' % task[0])

    # start merging relay_boards
    for task in merge_relay_boards(relay_boards_from_db, relay_boards_from_inv):
        if task[0] == 'insert':
            if verbose: print "insert relay_board", task[1]['fqdn']
            db.inventorysync.insert_relay_board(task[1])
        elif task[0] == 'delete':
            if verbose: print "delete relay_board", task[2]
            db.inventorysync.delete_relay_board(task[1])
        elif task[0] == 'update':
            if verbose: print "update relay_board", task[2]
            db.inventorysync.update_relay_board(task[1], task[2])
        else:
            raise RuntimeError('%s is not a task' % task[0])

def main():
    parser = argparse.ArgumentParser(description='Sync BMM with inventory.')
    parser.add_argument('--verbose', action='store_true',
                        default=False,
                        help='verbose output')
    parser.add_argument('--ship-it', action='store_true',
                        default=False,
                        help="Make large changes; don't use this flag in a crontask!")
    args = parser.parse_args()

    db = setup()
    sync(db, verbose=args.verbose, ship_it=args.ship_it)
