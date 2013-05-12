# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import sqlalchemy as sa
from mozpool.db import model
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    def test_dump_devices(self):
        self.add_server('server')
        ht_id = self.add_hardware_type('ht', 'hm')
        self.add_device('dev1', hardware_type_id=ht_id)
        self.add_device('dev2', hardware_type_id=ht_id)
        self.assertEqual(sorted(self.db.inventorysync.dump_devices()), sorted([
               {u'fqdn': u'dev1.example.com',
                u'hardware_model': u'hm',
                u'hardware_type': u'ht',
                u'id': 1,
                u'imaging_server': u'server',
                u'inventory_id': 1,
                u'mac_address': u'000000000000',
                u'name': u'dev1',
                u'relay_info': u''},
               {u'fqdn': u'dev2.example.com',
                u'hardware_model': u'hm',
                u'hardware_type': u'ht',
                u'id': 2,
                u'imaging_server': u'server',
                u'inventory_id': 2,
                u'mac_address': u'000000000000',
                u'name': u'dev2',
                u'relay_info': u''}
            ]))

    def test_insert_device(self):
        now = datetime.datetime(2013, 1, 1)
        self.add_hardware_type('panda', 'ES Rev B2')
        self.add_server('server1')
        self.db.inventorysync.insert_device(dict(
                name='device2', fqdn='device2.fqdn', inventory_id=23,
                mac_address='aabbccddeeff', imaging_server='server2',
                relay_info='relay-2:bank2:relay2',
                hardware_type='panda', hardware_model='ES Rev B2'),
                _now=now)
        # device with existing imaging_server and new hardware type to test the
        # insert-if-not-found behavior
        self.db.inventorysync.insert_device(dict(
                name='device3', fqdn='device3.fqdn', inventory_id=24,
                mac_address='aabbccddeeff', imaging_server='server1',
                relay_info='relay-2:bank2:relay2',
                hardware_type='tegra', hardware_model='blah'),
                _now=now)
        res = self.db.execute(model.devices.select())
        self.assertEquals(sorted([ dict(r) for r in res.fetchall() ]),
        sorted([
            {u'state': u'new', u'state_counters': u'{}', u'state_timeout': now,
             u'relay_info': u'relay-2:bank2:relay2', u'name': u'device2',
             u'fqdn': u'device2.fqdn', u'inventory_id': 23,
             u'imaging_server_id': 2, u'mac_address': u'aabbccddeeff', u'id': 1,
             u'image_id': None, u'boot_config': None,
             u'next_image_id': None, u'next_boot_config': None,
             u'comments': None, u'environment': None, u'hardware_type_id': 1},
            {u'state': u'new',u'state_counters': u'{}', u'state_timeout': now,
             u'relay_info': u'relay-2:bank2:relay2', u'name': u'device3',
             u'fqdn': u'device3.fqdn', u'inventory_id': 24,
             u'imaging_server_id': 1, u'mac_address': u'aabbccddeeff', u'id': 2,
             u'image_id': None, u'boot_config': None,
             u'next_image_id': None, u'next_boot_config': None,
             u'comments': None, u'environment': None, u'hardware_type_id': 2},
            ]))

    def test_delete_device(self):
        now = datetime.datetime.now()
        self.add_server('server1')
        id = self.add_device("device1", server="server1", relayinfo="relay-2:bank1:relay1")
        self.add_device("device2", server="server1", relayinfo="relay-2:bank1:relay1")
        self.db.execute(model.device_logs.insert(), [
            dict(device_id=1, ts=now, source='test', message='hi'),
            dict(device_id=1, ts=now, source='test', message='world'),
        ])
        self.db.inventorysync.delete_device(id)

        # check that both logs and devices were deleted
        res = self.db.execute(sa.select([model.devices.c.name]))
        self.assertEquals(res.fetchall(), [('device2',)])
        res = self.db.execute(model.device_logs.select())
        self.assertEquals(res.fetchall(), [])

    def test_update_device(self):
        self.add_server("server1")
        self.add_hardware_type("htyp", "hmod")
        self.add_device("device1", server="server1", relayinfo="relay-1:bank1:relay1")
        self.db.inventorysync.update_device(1, dict(fqdn='device1.fqdn', imaging_server='server9', mac_address='aabbccddeeff'))
        tbl = model.devices
        res = self.db.execute(sa.select([tbl.c.state, tbl.c.relay_info, tbl.c.fqdn, tbl.c.inventory_id,
                                         tbl.c.mac_address, tbl.c.imaging_server_id, tbl.c.hardware_type_id]))
        self.assertEquals([ dict(r) for r in res.fetchall() ], [
            {u'state': u'offline', u'relay_info': u'relay-1:bank1:relay1', u'fqdn': u'device1.fqdn',
             u'inventory_id': 1, u'mac_address': u'aabbccddeeff', u'imaging_server_id': 2,
             u'hardware_type_id': 1},
        ])

    def test_dump_relays(self):
        self.add_server('server')
        self.add_relay_board('relay1')
        self.add_relay_board('relay2')
        self.assertEqual(sorted(self.db.inventorysync.dump_relays()), sorted([
               {u'fqdn': u'relay1.example.com',
                u'id': 1,
                u'imaging_server': u'server',
                u'name': u'relay1'},
               {u'fqdn': u'relay2.example.com',
                u'id': 2,
                u'imaging_server': u'server',
                u'name': u'relay2'}
            ]))

    def test_insert_relay_board(self):
        now = datetime.datetime(2013, 1, 1)
        self.add_server('server1')
        self.db.inventorysync.insert_relay_board(dict(
                name='relay2', fqdn='relay2.fqdn',
                imaging_server='server2'),
                _now=now)
        # device with existing imaging_server and new hardware type to test the
        # insert-if-not-found behavior
        self.db.inventorysync.insert_relay_board(dict(
                name='relay3', fqdn='relay3.fqdn',
                imaging_server='server1'),
                _now=now)
        res = self.db.execute(model.relay_boards.select())
        self.assertEquals(sorted([ dict(r) for r in res.fetchall() ]),
        sorted([
            {u'state': u'ready', u'state_counters': u'{}', u'state_timeout': now,
             u'name': u'relay2', u'fqdn': u'relay2.fqdn',
             u'imaging_server_id': 2, u'id': 1},
            {u'state': u'ready', u'state_counters': u'{}', u'state_timeout': now,
             u'name': u'relay3', u'fqdn': u'relay3.fqdn',
             u'imaging_server_id': 1, u'id': 2},
            ]))

    def test_delete_relay_board(self):
        now = datetime.datetime.now()
        self.add_server('server1')
        id = self.add_relay_board("relay1", server="server1")
        self.add_relay_board("relay2", server="server1")
        self.db.inventorysync.delete_relay_board(id)
        res = self.db.execute(sa.select([model.relay_boards.c.name]))
        self.assertEquals(res.fetchall(), [('relay2',)])

    def test_update_relay_board(self):
        self.add_server("server1")
        self.add_relay_board("relay1", server="server1")
        self.db.inventorysync.update_relay_board(1, dict(fqdn='relay1.fqdn', imaging_server='server4'))
        res = self.db.execute(sa.select([model.relay_boards.c.state, model.relay_boards.c.fqdn,
                                         model.relay_boards.c.imaging_server_id]))
        self.assertEquals([ dict(r) for r in res.fetchall() ], [
            {u'state': u'offline', u'fqdn': u'relay1.fqdn',
             u'imaging_server_id': 2},
        ])

    def test_update_device_hardware_type(self):
        self.add_server("server1")
        self.add_hardware_type("htyp", "hmod")
        self.add_device("device1", server="server1", relayinfo="relay-1:bank1:relay1")
        self.db.inventorysync.update_device(1, dict(fqdn='device1.fqdn', imaging_server='server9',
            mac_address='aabbccddeeff', hardware_type='samsung', hardware_model='galaxy',
            id=999)) # note id is ignored
        tbl = model.devices
        res = self.db.execute(sa.select([tbl.c.relay_info, tbl.c.hardware_type_id]))
        self.assertEquals([dict(r) for r in res.fetchall()], [
            {u'relay_info': u'relay-1:bank1:relay1', u'hardware_type_id': 2},
        ])
