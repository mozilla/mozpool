#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import requests
from bmm import data
from bmm import config

# systems are represented as a dict with keys:
#  - id (only for dicts from the database)
#  - name
#  - fqdn
#  - inventory_id
#  - mac_address (from nic.0.mac_address.0)
#  - imaging_server (from system.imaging_server.0)
#  - relay_info (from system.relay.0)

def get_boards(url, filter, username, password, verbose=False):
    """
    Generate a list of hosts from inventory.  FILTER is a tastypie-style filter for
    the desired hosts.  Any hosts without 'system.relay.0' are ignored.
    """
    path = '/en-US/tasty/v3/system/?' + filter
    while path:
        r = requests.get(url + path, auth=(username, password))
        if r.status_code != requests.codes.ok:
            raise RuntimeError('got status code %s from inventory' % r.status_code)

        for o in r.json['objects']:
            hostname = o['hostname']

            kv = dict([ (kv['key'], kv['value']) for kv in o['key_value'] ])
            required_keys = 'system.relay.0', 'nic.0.mac_address.0', 'system.imaging_server.0'
            missing = [ k for k in required_keys if k not in kv ]
            if missing:
                if verbose: print hostname, 'SKIPPED - missing k/v value(s)', ' '.join(missing)
                continue

            name = hostname.split('.', 1)[0]
            mac_address = kv['nic.0.mac_address.0'].replace(':', '').lower()
            yield dict(
                name=name,
                fqdn=hostname,
                inventory_id=o['id'],
                mac_address=mac_address,
                imaging_server=kv['system.imaging_server.0'],
                relay_info=kv['system.relay.0'])

            if verbose: print hostname, 'downloaded.'

        # go on to the next set of hosts
        path = r.json['meta']['next']

def merge_boards(from_db, from_inv):
    """
    Merge a list of hosts in the DB with those in inventory.  This yields a
    list of instructions of the form ('insert', dict), ('delete', id), or
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

def sync(verbose=False):
    from_db = data.dump_boards()
    from_inv = get_boards(
            config.inventory_url(),
            # TODO: use a better filter that can look for k/v entries indicating systems
            # are managed by an imaging server
            'hostname__startswith=panda-',
            config.inventory_username(),
            config.inventory_password(),
            verbose=verbose)

    for task in merge_boards(from_db, from_inv):
        if task[0] == 'insert':
            if verbose: print "insert board", task[1]['fqdn']
            data.insert_board(task[1])
        elif task[0] == 'delete':
            if verbose: print "delete board", task[2]
            data.delete_board(task[1])
        elif task[0] == 'update':
            if verbose: print "update board", task[2]
            data.update_board(task[1], task[2])
        else:
            raise AssertionError('%s is not a task' % task[0])

def main():
    parser = argparse.ArgumentParser(description='Sync BMM with inventory.')
    parser.add_argument('--verbose', action='store_true',
                               default=False,
                               help='verbose output')
    args = parser.parse_args()

    sync(verbose=args.verbose)
