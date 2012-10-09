#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import sys
import unittest
import json
import hashlib
import socket
import requests
import tempfile
import mock
from mock import patch
from paste.fixture import TestApp

sys.path.append(os.path.join(os.getcwd(), "server"))

from bmm import server
from bmm import data
from bmm import model
from bmm import relay
from bmm import testing
from bmm import invsync
from bmm import config
from bmm.testing import add_server, add_board, add_bootimage

class ConfigMixin(object):
    def setUp(self):
        self.dbfile = tempfile.NamedTemporaryFile()
        testing.create_sqlite_db(self.dbfile.name, schema=True)
        self.app = TestApp(server.get_app().wsgifunc())

    def tearDown(self):
        data.get_conn().close()
        del self.dbfile
        data.engine = None

@patch("socket.getfqdn")
class TestData(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestData, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", relayinfo="relay-1:bank1:relay1")

    def testRelayInfo(self, Mock):
        Mock.return_value = "server1"
        self.assertEquals(("relay-1", 1, 1),
                          data.board_relay_info("board1"))

    def testDumpBoards(self, Mock):
        self.assertEquals([
            dict(id=1, name='board1', fqdn='board1', inventory_id=1, mac_address='000000000000',
                imaging_server='server1', relay_info='relay-1:bank1:relay1'),
            ],
            data.dump_boards())

    def testInsertBoard(self, Mock):
        data.insert_board(dict(name='board2', fqdn='board2.fqdn', inventory_id=23,
            mac_address='aabbccddeeff', imaging_server='server2',
                relay_info='relay-2:bank2:relay2'))
        # board with existing imaging_server to test the insert-if-not-found behavior
        data.insert_board(dict(name='board3', fqdn='board3.fqdn', inventory_id=24,
            mac_address='aabbccddeeff', imaging_server='server1',
                relay_info='relay-2:bank2:relay2'))
        conn = data.get_conn()
        res = conn.execute(model.boards.select())
        self.assertEquals(sorted([ dict(r) for r in res.fetchall() ]),
        sorted([
            {u'status': u'new', u'relay_info': u'relay-2:bank2:relay2', u'name': u'board2',
             u'fqdn': u'board2.fqdn', u'inventory_id': 23, u'imaging_server_id': 2,
             u'boot_config': None, u'mac_address': u'aabbccddeeff', u'id': 2},
            {u'status': u'new', u'relay_info': u'relay-2:bank2:relay2', u'name': u'board3',
             u'fqdn': u'board3.fqdn', u'inventory_id': 24, u'imaging_server_id': 1,
             u'boot_config': None, u'mac_address': u'aabbccddeeff', u'id': 3},
            {u'status': u'offline', u'relay_info': u'relay-1:bank1:relay1', u'name': u'board1',
             u'fqdn': u'board1', u'inventory_id': 1, u'imaging_server_id': 1,
             u'boot_config': u'{}', u'mac_address': u'000000000000', u'id': 1},
            ]))

    def testDeleteBoard(self, Mock):
        conn = data.get_conn()
        data.delete_board(1)
        res = conn.execute(model.boards.select())
        self.assertEquals(res.fetchall(), [])

    def testUpdateBoard(self, Mock):
        conn = data.get_conn()
        data.update_board(1, dict(fqdn='board1.fqdn', imaging_server='server9', mac_address='aabbccddeeff'))
        res = conn.execute(model.boards.select())
        self.assertEquals([ dict(r) for r in res.fetchall() ], [
            {u'status': u'offline', u'relay_info': u'relay-1:bank1:relay1', u'name': u'board1',
             u'fqdn': u'board1.fqdn', u'inventory_id': 1, u'imaging_server_id': 2,
             u'boot_config': u'{}', u'mac_address': u'aabbccddeeff', u'id': 1},
        ])

@patch("socket.getfqdn")
class TestBoardList(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardList, self).setUp()
        add_server("server1")
        add_board("board1", server="server1")
        add_board("board2", server="server1")
        add_server("server2")
        add_board("board3", server="server2")
        add_board("board4", server="server2")

    def testBoardList(self, Mock):
        Mock.return_value = "server1"
        r = self.app.get("/api/board/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("boards" in body)
        self.assertTrue("board1" in body["boards"])
        self.assertTrue("board2" in body["boards"])

        Mock.return_value = "server2"
        r = self.app.get("/api/board/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("boards" in body)
        self.assertTrue("board3" in body["boards"])
        self.assertTrue("board4" in body["boards"])

@patch("socket.getfqdn")
class TestBoardStatus(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardStatus, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", state="running")
        add_board("board2", server="server1", state="freaking_out")

    def testBoardStatus(self, Mock):
        Mock.return_value = "server1"
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["state"])

        r = self.app.get("/api/board/board2/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("freaking_out", body["state"])

    def testSetBoardStatus(self, Mock):
        Mock.return_value = "server1"
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["state"])

        r = self.app.post("/api/board/board1/status/",
                          headers={"Content-Type": "application/json"},
                          params='{"state":"offline"}')
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("offline", body["state"])

@patch("socket.getfqdn")
class TestBoardConfig(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardConfig, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", config={"abc": "xyz"})

    def testBoardConfig(self, Mock):
        Mock.return_value = "server1"
        r = self.app.get("/api/board/board1/config/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals({"abc": "xyz"}, json.loads(body["config"]))

@patch("socket.getfqdn")
class TestBoardBoot(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardBoot, self).setUp()
        add_server("server1")
        add_board("board1", server="server1")
        add_board("board2", server="server1")

    def testBoardBoot(self, Mock):
        #TODO
        pass

@patch("socket.socket")
@patch("socket.getfqdn")
class TestBoardReboot(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardReboot, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", state="running",
                  relayinfo="relay-1:bank1:relay1")

    def testBoardReboot(self, Mockfqdn, MockSocket):
        Mockfqdn.return_value = "server1"
        MockSocketRecv = MockSocket.return_value.recv
        # reboot will do two sets, each followed by a get, so mock
        # the responses it would receive from the relay board
        MockSocketRecv.side_effect = [relay.COMMAND_OK,
                                      chr(1),
                                      relay.COMMAND_OK,
                                      chr(0)]
        r = self.app.post("/api/board/board1/reboot/")
        self.assertEqual(204, r.status)
        # Nothing in the response body currently
        self.assertEqual("relay-1",
                         MockSocket.return_value.connect.call_args[0][0][0])
        self.assertEqual(4, MockSocketRecv.call_count)

        # Verify that it got put into the rebooting state
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("rebooting", body["state"])

class TestBoardRedirects(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardRedirects, self).setUp()
        add_server("server1")
        add_server("server2")
        add_board("board1", server="server1")
        add_board("board2", server="server2")

    @patch("socket.getfqdn")
    def testRedirectBoard(self, Mock):
        Mock.return_value = "server1"
        r = self.app.get("/api/board/board2/status/")
        self.assertEqual(302, r.status)
        self.assertEqual("http://server2/api/board/board2/status/",
                         r.header("Location"))

class TestInvSyncMerge(unittest.TestCase):

    def setUp(self):
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
            relay_info="relay-1:bank2:relay2")
        self.panda2_db = self.panda2_inv.copy()
        self.panda2_db['id'] = 402

    def test_merge_boards_no_change(self):
        commands = list(invsync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [])

    def test_merge_boards_insert(self):
        commands = list(invsync.merge_boards(
            [self.panda1_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [
            ('insert', self.panda2_inv),
        ])

    def test_merge_boards_delete(self):
        commands = list(invsync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', 401, self.panda1_db),
        ])

    def test_merge_boards_update(self):
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(invsync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('update', 402, self.panda2_inv),
        ])

    def test_merge_boards_combo(self):
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(invsync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', 401, self.panda1_db),
            ('update', 402, self.panda2_inv),
        ])

@patch('requests.get')
class TestInvSyncGet(unittest.TestCase):

    def set_responses(self, chunks):
        # patch out requests.get to keep the urls it was called with,
        # and to return responses of hosts as set with addChunk
        paths = [ '/path%d' % i for i in range(len(chunks)) ]
        def get(url, auth):
            chunk = chunks.pop(0)
            paths.pop(0)
            r = mock.Mock(spec=requests.Response)
            r.status_code = 200
            r.json = dict(
                meta=dict(next=paths[0] if paths else None),
                objects=chunk)
            return r
        requests.get.configure_mock(side_effect=get)

    def make_host(self, name, mac_address=True, imaging_server=True, relay_info=True):
        # make deterministic values
        fqdn = '%s.vlan.dc.mozilla.com' % name
        inventory_id = hash(fqdn) % 100
        kv = []
        if mac_address:
            mac_address = hashlib.md5(fqdn).digest()[:6]
            mac_address = ':'.join([ '%02x' % ord(b) for b in mac_address ])
            kv.append(dict(key='nic.0.mac_address.0', value=mac_address))
        if imaging_server:
            imaging_server = 'img%d' % ((hash(fqdn) / 100) % 10)
            kv.append(dict(key='system.imaging_server.0', value=imaging_server))
        if relay_info:
            relay_info = 'relay%d' % ((hash(fqdn) / 1000) % 10)
            kv.append(dict(key='system.relay.0', value=relay_info))
        return dict(
            hostname=fqdn,
            id=inventory_id,
            key_value=kv)

    def test_one_response(self, get):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002') ],
        ])
        hosts = list(invsync.get_boards('https://inv', 'filter', 'me', 'pass'))
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com'},
            {'inventory_id': 97, 'relay_info': 'relay9', 'name': 'panda-002',
             'imaging_server': 'img1', 'mac_address': '86a1c8ce6ea2',
             'fqdn': 'panda-002.vlan.dc.mozilla.com'},
        ])
        self.assertEqual(requests.get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?filter', auth=('me', 'pass')),
        ])

    def test_loop_and_filtering(self, get):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002', imaging_server=False) ],
            [ self.make_host('panda-003'), self.make_host('panda-004', relay_info=False) ],
            [ self.make_host('panda-005'), self.make_host('panda-006', mac_address=False) ],
        ])
        hosts = list(invsync.get_boards('https://inv', 'filter', 'me', 'pass'))
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com'},
            # panda-002 was skipped
            {'inventory_id': 52, 'relay_info': 'relay4', 'name': 'panda-003',
             'imaging_server': 'img9', 'mac_address': 'aec31326594a',
             'fqdn': 'panda-003.vlan.dc.mozilla.com'},
            # panda-004 was skipped
            {'inventory_id': 6, 'relay_info': 'relay9', 'name': 'panda-005',
             'imaging_server': 'img3', 'mac_address': 'c19b00f9644b',
             'fqdn': 'panda-005.vlan.dc.mozilla.com'}
            # panda-006 was skipped
        ])
        self.assertEqual(requests.get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?filter', auth=('me', 'pass')),
            mock.call('https://inv/path1', auth=('me', 'pass')),
            mock.call('https://inv/path2', auth=('me', 'pass')),
        ])

@patch('bmm.data.dump_boards')
@patch('bmm.data.insert_board')
@patch('bmm.data.update_board')
@patch('bmm.data.delete_board')
@patch('bmm.invsync.get_boards')
@patch('bmm.invsync.merge_boards')
class TestInvSyncSync(unittest.TestCase):

    def test_sync(self, merge_boards, get_boards, delete_board,
                        update_board, insert_board, dump_boards):
        config.set_config(inventory_url='http://foo/', inventory_username='u', inventory_password='p')
        dump_boards.return_value = 'dumped boards'
        get_boards.return_value = 'gotten boards'
        merge_boards.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        invsync.sync()
        dump_boards.assert_called_with()
        get_boards.assert_called_with('http://foo/', 'hostname__startswith=panda-', 'u', 'p', verbose=False)
        merge_boards.assert_called_with('dumped boards', 'gotten boards')
        insert_board.assert_called_with(dict(insert=1))
        delete_board.assert_called_with(10)
        update_board.assert_called_with(11, dict(update=3))

if __name__ == "__main__":
    unittest.main()
