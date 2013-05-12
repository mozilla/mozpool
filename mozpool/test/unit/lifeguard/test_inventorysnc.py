# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import requests
import hashlib
from mozpool.lifeguard import inventorysync
from mozpool import config
from mozpool.test.util import TestCase, PatchMixin, DBMixin, ConfigMixin, ScriptMixin

class Tests(DBMixin, ConfigMixin, PatchMixin, ScriptMixin, TestCase):

    auto_patch = [
        ('requests_get', 'requests.get'),
        ('dump_devices', 'mozpool.db.inventorysync.Methods.dump_devices'),
        ('insert_device', 'mozpool.db.inventorysync.Methods.insert_device'),
        ('update_device', 'mozpool.db.inventorysync.Methods.update_device'),
        ('delete_device', 'mozpool.db.inventorysync.Methods.delete_device'),
        ('dump_relays', 'mozpool.db.inventorysync.Methods.dump_relays'),
        ('insert_relay_board', 'mozpool.db.inventorysync.Methods.insert_relay_board'),
        ('update_relay_board', 'mozpool.db.inventorysync.Methods.update_relay_board'),
        ('delete_relay_board', 'mozpool.db.inventorysync.Methods.delete_relay_board'),
    ]

    # test merge_devices

    def make_pandas(self):
        self.panda1_inv = dict(
            name='panda-0001',
            fqdn='panda-0001.r402-4.scl3.mozilla.com',
            inventory_id=201,
            mac_address='aabbccddeeff',
            imaging_server='mobile-services1',
            relay_info="relay-1:bank1:relay1")
        self.panda1_db = self.panda1_inv.copy()
        self.panda1_db['id'] = 401

        self.panda2_inv = dict(
            name='panda-0002',
            fqdn='panda-0002.r402-4.scl3.mozilla.com',
            inventory_id=202,
            mac_address='112233445566',
            imaging_server='mobile-services2',
            relay_info="relay-2.fqdn:bank2:relay2")
        self.panda2_db = self.panda2_inv.copy()
        self.panda2_db['id'] = 402

        self.panda3_inv = dict(
            name='panda-0003',
            fqdn='panda-0003.r402-4.scl3.mozilla.com',
            inventory_id=203,
            mac_address='ffeeddccbbaa',
            imaging_server='mobile-services2',
            relay_info="relay-1:bank3:relay3")
        self.panda3_db = self.panda3_inv.copy()
        self.panda3_db['id'] = 403

    def test_merge_devices_no_change(self):
        self.make_pandas()
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [])

    def test_merge_devices_insert(self):
        self.make_pandas()
        commands = list(inventorysync.merge_devices(
            [self.panda1_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [
            ('insert', self.panda2_inv),
        ])

    def test_merge_devices_delete(self):
        self.make_pandas()
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', 401, self.panda1_db),
        ])

    def test_merge_devices_update(self):
        self.make_pandas()
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('update', 402, self.panda2_inv),
        ])

    def test_merge_devices_combo(self):
        self.make_pandas()
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', 401, self.panda1_db),
            ('update', 402, self.panda2_inv),
        ])

    # test merge_relay_boards

    def make_relay_boards(self):
        self.relay1_inv = dict(
            name='relay-001',
            fqdn='relay-001.r402-4.scl3.mozilla.com',
            imaging_server='mobile-services1')
        self.relay1_db = self.relay1_inv.copy()
        self.relay1_db['id'] = 123

        self.relay2_inv = dict(
            name='relay-002',
            fqdn='relay-002.r402-4.scl3.mozilla.com',
            imaging_server='mobile-services2')
        self.relay2_db = self.relay2_inv.copy()
        self.relay2_db['id'] = 321

    def test_merge_relay_boards_no_change(self):
        self.make_relay_boards()
        commands = list(inventorysync.merge_relay_boards(
            [self.relay1_db, self.relay2_db],
            [self.relay1_inv, self.relay2_inv]))
        self.assertEqual(commands, [])

    def test_merge_relay_boards_insert(self):
        self.make_relay_boards()
        commands = list(inventorysync.merge_relay_boards(
            [self.relay1_db],
            [self.relay1_inv, self.relay2_inv]))
        self.assertEqual(commands, [
            ('insert', self.relay2_inv),
        ])

    def test_merge_relay_boards_delete(self):
        self.make_relay_boards()
        commands = list(inventorysync.merge_relay_boards(
            [self.relay1_db, self.relay2_db],
            [self.relay2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', self.relay1_db['id'], self.relay1_db),
        ])

    def test_merge_relay_boards_update(self):
        self.make_relay_boards()
        self.relay2_inv['imaging_server'] = 'mobile-services1'
        commands = list(inventorysync.merge_relay_boards(
            [self.relay1_db, self.relay2_db],
            [self.relay1_inv, self.relay2_inv]))
        self.assertEqual(sorted(commands), [
            ('update', self.relay2_db['id'], self.relay2_inv),
        ])

    def test_merge_relay_boards_combo(self):
        self.make_relay_boards()
        self.relay2_inv['imaging_server'] = 'mobile-services'
        commands = list(inventorysync.merge_relay_boards(
            [self.relay1_db, self.relay2_db],
            [self.relay2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', self.relay1_db['id'], self.relay1_db),
            ('update', self.relay2_db['id'], self.relay2_inv),
        ])

    # test get_relay_boards

    def test_get_relay_boards(self):
        self.make_pandas()
        device_list_from_inv = [self.panda1_inv, self.panda2_inv]
        relay_board_list = inventorysync.get_relay_boards(device_list_from_inv)
        self.assertEqual( sorted(relay_board_list), sorted([{'fqdn': 'relay-2.fqdn',
                                            'imaging_server': 'mobile-services2',
                                            'name': 'relay-2'},
                                            {'fqdn': 'relay-1',
                                            'imaging_server': 'mobile-services1',
                                            'name': 'relay-1'}]))

    def test_get_relay_boards_raise_runtime_error(self):
        self.make_pandas()
        self.assertRaises(RuntimeError, lambda: inventorysync.get_relay_boards([self.panda1_inv,
                                                                                self.panda3_inv]))

    # test get_devices

    def set_responses(self, chunks, status_code=200):
        # patch out requests.get to keep the urls it was called with,
        # and to return responses of hosts as set with addChunk
        paths = [ '/path%d' % i for i in range(len(chunks)) ]
        def get(url, auth):
            chunk = chunks.pop(0)
            paths.pop(0)
            r = mock.Mock(spec=requests.Response)
            r.status_code = status_code
            r.json = lambda : dict(
                meta=dict(next=paths[0] if paths else None),
                objects=chunk)
            return r
        self.requests_get.configure_mock(side_effect=get)

    def make_host(self, name, want_mac_address=True, want_imaging_server=True, want_relay_info=True,
            server_model_vendor='PandaBoard', server_model_model='ES'):
        # make deterministic values
        fqdn = '%s.vlan.dc.mozilla.com' % name
        inventory_id = hash(fqdn) % 100
        kv = []
        if want_mac_address:
            mac_address = hashlib.md5(fqdn).digest()[:6]
            mac_address = ':'.join([ '%02x' % ord(b) for b in mac_address ])
            kv.append(dict(key='nic.0.mac_address.0', value=mac_address))
        if want_imaging_server:
            imaging_server = 'img%d' % ((hash(fqdn) / 100) % 10)
            kv.append(dict(key='system.imaging_server.0', value=imaging_server))
        if want_relay_info:
            relay_info = 'relay%d' % ((hash(fqdn) / 1000) % 10)
            kv.append(dict(key='system.relay.0', value=relay_info))
        server_model = {'model' : server_model_model, 'vendor' : server_model_vendor}
        return dict(
            hostname=fqdn,
            id=inventory_id,
            key_value=kv,
            server_model=server_model)

    def test_one_response(self):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002') ],
        ])
        hosts = inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', None)
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com', 'hardware_type': 'PandaBoard',
             'hardware_model': 'ES'},
            {'inventory_id': 97, 'relay_info': 'relay9', 'name': 'panda-002',
             'imaging_server': 'img1', 'mac_address': '86a1c8ce6ea2',
             'fqdn': 'panda-002.vlan.dc.mozilla.com', 'hardware_type': 'PandaBoard',
             'hardware_model': 'ES'},
        ])
        self.assertEqual(self.requests_get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
        ])

    def test_re_filter(self):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002') ],
        ])
        hosts = inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', '.*9')
        self.assertEqual(hosts, [
            # panda-001 was skipped, since 'img9' matches '.*9'
            {'inventory_id': 97, 'relay_info': 'relay9', 'name': 'panda-002',
             'imaging_server': 'img1', 'mac_address': '86a1c8ce6ea2',
             'fqdn': 'panda-002.vlan.dc.mozilla.com', 'hardware_type': 'PandaBoard',
             'hardware_model': 'ES'},
        ])
        self.assertEqual(self.requests_get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
        ])

    def test_loop_and_filtering(self):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002', want_imaging_server=False) ],
            [ self.make_host('panda-003'), self.make_host('panda-004', want_relay_info=False) ],
            [ self.make_host('panda-005'), self.make_host('panda-006', want_mac_address=False) ],
        ])
        hosts = inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', None, verbose=True)
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com', 'hardware_type': 'PandaBoard',
             'hardware_model': 'ES'},
            # panda-002 was skipped
            {'inventory_id': 52, 'relay_info': 'relay4', 'name': 'panda-003',
             'imaging_server': 'img9', 'mac_address': 'aec31326594a',
             'fqdn': 'panda-003.vlan.dc.mozilla.com', 'hardware_type': 'PandaBoard',
             'hardware_model': 'ES'},
            # panda-004 was skipped
            {'inventory_id': 6, 'relay_info': 'relay9', 'name': 'panda-005',
             'imaging_server': 'img3', 'mac_address': 'c19b00f9644b',
             'fqdn': 'panda-005.vlan.dc.mozilla.com', 'hardware_type': 'PandaBoard',
             'hardware_model': 'ES'}
            # panda-006 was skipped
        ])
        self.assertEqual(self.requests_get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
            mock.call('https://inv/path1', auth=('me', 'pass')),
            mock.call('https://inv/path2', auth=('me', 'pass')),
        ])

    def test_get_devices_requests_error(self):
        self.set_responses([[]], status_code=500)
        self.assertRaises(RuntimeError, lambda :
            inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', None))

    # test sync

    @mock.patch('mozpool.lifeguard.inventorysync.merge_relay_boards')
    @mock.patch('mozpool.lifeguard.inventorysync.get_relay_boards')
    @mock.patch('mozpool.lifeguard.inventorysync.get_devices')
    @mock.patch('mozpool.lifeguard.inventorysync.merge_devices')
    def test_sync(self, merge_devices, get_devices, get_relay_boards, merge_relay_boards):
        config.set('inventory', 'url', 'http://foo/')
        config.set('inventory', 'filter', 'hostname__startswith=panda-')
        config.set('inventory', 'username', 'u')
        config.set('inventory', 'password', 'p')
        self.dump_devices.return_value = 'dumped devices'
        get_devices.return_value = 'gotten devices'
        merge_devices.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        get_relay_boards.return_value = 'gotten relay_boards'
        self.dump_relays.return_value = 'dumped relays'
        merge_relay_boards.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        inventorysync.sync(self.db)
        self.dump_devices.assert_called_with()
        get_devices.assert_called_with('http://foo/', 'hostname__startswith=panda-', 'u', 'p', None,
                verbose=False)
        merge_devices.assert_called_with('dumped devices', 'gotten devices')
        self.insert_device.assert_called_with(dict(insert=1))
        self.delete_device.assert_called_with(10)
        self.update_device.assert_called_with(11, dict(update=3))
        get_relay_boards.assert_called_with(get_devices.return_value)
        self.dump_relays.assert_called_with()
        merge_relay_boards.assert_called_with(self.dump_relays.return_value, get_relay_boards.return_value)
        self.insert_relay_board.assert_called_with(dict(insert=1))
        self.delete_relay_board.assert_called_with(10)
        self.update_relay_board.assert_called_with(11, dict(update=3))

    @mock.patch('mozpool.lifeguard.inventorysync.merge_relay_boards')
    @mock.patch('mozpool.lifeguard.inventorysync.get_relay_boards')
    @mock.patch('mozpool.lifeguard.inventorysync.get_devices')
    @mock.patch('mozpool.lifeguard.inventorysync.merge_devices')
    def test_sync_with_res(self, merge_devices, get_devices, get_relay_boards, merge_relay_boards):
        config.set('inventory', 'url', 'http://foo/')
        config.set('inventory', 'filter', 'hostname__startswith=panda-')
        config.set('inventory', 'username', 'u')
        config.set('inventory', 'password', 'p')
        config.set('inventory', 'ignore_devices_on_servers_re', 're')
        self.dump_devices.return_value = 'dumped devices'
        get_devices.return_value = 'gotten devices'
        merge_devices.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        get_relay_boards.return_value = 'gotten relay_boards'
        self.dump_relays.return_value = 'dumped relays'
        merge_relay_boards.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        inventorysync.sync(self.db)
        self.dump_devices.assert_called_with()
        get_devices.assert_called_with('http://foo/', 'hostname__startswith=panda-', 'u', 'p', 're',
                verbose=False)
        merge_devices.assert_called_with('dumped devices', 'gotten devices')
        self.insert_device.assert_called_with(dict(insert=1))
        self.delete_device.assert_called_with(10)
        self.update_device.assert_called_with(11, dict(update=3))
        get_relay_boards.assert_called_with(get_devices.return_value)
        self.dump_relays.assert_called_with()
        merge_relay_boards.assert_called_with(self.dump_relays.return_value, get_relay_boards.return_value)
        self.insert_relay_board.assert_called_with(dict(insert=1))
        self.delete_relay_board.assert_called_with(10)
        self.update_relay_board.assert_called_with(11, dict(update=3))

    # test the script

    @mock.patch('mozpool.lifeguard.inventorysync.sync')
    def test_script(self, sync):
        inventorysync.setup = lambda : self.db
        self.assertEqual(self.run_script(inventorysync.main, []), None)
        sync.assert_called_with(self.db, verbose=False)
