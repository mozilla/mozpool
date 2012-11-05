#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import unittest
import json
import hashlib
import shutil
import requests
import tempfile
import mock
import datetime
import threading
from mock import patch
from paste.fixture import TestApp

from mozpool import config
from mozpool import statemachine
from mozpool import util
from mozpool.web import server
from mozpool.db import data
from mozpool.db import model
from mozpool.bmm import relay
from mozpool.lifeguard import inventorysync
from mozpool.test.util import add_server, add_board, add_bootimage, setup_db

class ConfigMixin(object):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.dbfile = os.path.join(self.tempdir, "sqlite.db")
        tftp_root = os.path.join(self.tempdir, "tftp")
        os.mkdir(tftp_root)
        image_store = os.path.join(self.tempdir, "images")
        os.mkdir(image_store)
        # set up the config with defaults
        config.reset()
        config.set('database', 'engine', 'sqlite:///' + self.dbfile)
        config.set('server', 'fqdn', 'server1')
        config.set('paths', 'tftp_root', tftp_root)
        config.set('paths', 'image_store', image_store)
        # set up the db
        setup_db(self.dbfile)
        self.app = TestApp(server.get_app().wsgifunc())

    def tearDown(self):
        data.get_conn().close()
        data.engine = None
        shutil.rmtree(self.tempdir)

class TestData(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestData, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", relayinfo="relay-1:bank1:relay1")

    def testRelayInfo(self):
        self.assertEquals(("relay-1", 1, 1),
                          data.board_relay_info("board1"))

    def testDumpBoards(self):
        self.assertEquals([
            dict(id=1, name='board1', fqdn='board1', inventory_id=1, mac_address='000000000000',
                imaging_server='server1', relay_info='relay-1:bank1:relay1', status='offline'),
            ],
            data.dump_boards())

    def testInsertBoard(self):
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

    def testDeleteBoard(self):
        conn = data.get_conn()
        now = datetime.datetime.now()
        conn.execute(model.logs.insert(), [
            dict(board_id=1, ts=now, source='test', message='hi'),
            dict(board_id=1, ts=now, source='test', message='world'),
        ])
        data.delete_board(1)

        # check that both logs and boards were deleted
        res = conn.execute(model.boards.select())
        self.assertEquals(res.fetchall(), [])
        res = conn.execute(model.logs.select())
        self.assertEquals(res.fetchall(), [])

    def testUpdateBoard(self):
        conn = data.get_conn()
        data.update_board(1, dict(fqdn='board1.fqdn', imaging_server='server9', mac_address='aabbccddeeff'))
        res = conn.execute(model.boards.select())
        self.assertEquals([ dict(r) for r in res.fetchall() ], [
            {u'status': u'offline', u'relay_info': u'relay-1:bank1:relay1', u'name': u'board1',
             u'fqdn': u'board1.fqdn', u'inventory_id': 1, u'imaging_server_id': 2,
             u'boot_config': u'{}', u'mac_address': u'aabbccddeeff', u'id': 1},
        ])

class TestBoardList(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardList, self).setUp()
        add_server("server1")
        add_board("board1", server="server1")
        add_board("board2", server="server1")
        add_server("server2")
        add_board("board3", server="server2")
        add_board("board4", server="server2")

    def testBoardList(self):
        """
        /board/list/ should list all boards for all servers.
        """
        r = self.app.get("/api/board/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("boards" in body)
        self.assertTrue("board1" in body["boards"])
        self.assertTrue("board2" in body["boards"])
        self.assertTrue("board3" in body["boards"])
        self.assertTrue("board4" in body["boards"])

        r = self.app.get("/api/board/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("boards" in body)
        self.assertTrue("board1" in body["boards"])
        self.assertTrue("board2" in body["boards"])
        self.assertTrue("board3" in body["boards"])
        self.assertTrue("board4" in body["boards"])

class TestBoardStatus(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardStatus, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", status="running")
        add_board("board2", server="server1", status="freaking_out")
        add_server("server2")
        add_board("board3", server="server2", status="running")

    def testBoardStatus(self):
        """
        /board/status/ should work for any board on any server.
        """
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["status"])

        r = self.app.get("/api/board/board2/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("freaking_out", body["status"])

        r = self.app.get("/api/board/board3/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["status"])

    def testSetBoardStatus(self):
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["status"])

        r = self.app.post("/api/board/board1/status/",
                          headers={"Content-Type": "application/json"},
                          params='{"status":"offline"}')
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("offline", body["status"])

class TestBoardConfig(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardConfig, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", config={"abc": "xyz"})

    def testBoardConfig(self):
        r = self.app.get("/api/board/board1/config/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals({"abc": "xyz"}, body["config"])

@patch("socket.socket")
class TestBoardBoot(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardBoot, self).setUp()
        add_server("server1")
        self.board_mac = "001122334455"
        add_board("board1", server="server1", status="running",
                  mac_address=self.board_mac,
                  relayinfo="relay-1:bank1:relay1")
        self.pxefile = "image1"
        # create a file for the boot image.
        open(os.path.join(config.get('paths', 'image_store'), self.pxefile), "w").write("abc")
        add_bootimage("image1", pxe_config_filename=self.pxefile)

    def testBoardBoot(self, MockSocket):
        MockSocketRecv = MockSocket.return_value.recv
        # reboot will do two sets, each followed by a get, so mock
        # the responses it would receive from the relay board
        MockSocketRecv.side_effect = [relay.COMMAND_OK,
                                      chr(1),
                                      relay.COMMAND_OK,
                                      chr(0)]

        config_data = {"foo":"bar"}
        r = self.app.post("/api/board/board1/boot/image1/",
                          headers={"Content-Type": "application/json"},
                          params=json.dumps(config_data))
        self.assertEqual(200, r.status)
        # Nothing in the response body currently

        # Verify that it got put into the boot-initiated state
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("boot-initiated", body["status"])

        # Verify that the config data was set properly.
        r = self.app.get("/api/board/board1/config/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals(config_data, body["config"])

        # Verify that the symlink was created in tftp_root
        mac = data.mac_with_dashes(self.board_mac)
        tftp_link = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg",
                                 "01-" + mac)
        self.assertTrue(os.path.islink(tftp_link))

        # Verify that it links to the right PXE image.
        self.assertEqual(self.pxefile, os.path.basename(os.readlink(tftp_link)))

        self.assertNotEqual(None, MockSocket.return_value.connect.call_args)
        self.assertEqual("relay-1",
                         MockSocket.return_value.connect.call_args[0][0][0])
        self.assertEqual(4, MockSocketRecv.call_count)

        # Lazy, just test this here
        r = self.app.post("/api/board/board1/bootcomplete/")
        self.assertEqual(200, r.status)
        self.assertFalse(os.path.exists(tftp_link))

@patch("socket.socket")
class TestBoardReboot(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardReboot, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", status="running",
                  relayinfo="relay-1:bank1:relay1")

    def testBoardReboot(self, MockSocket):
        MockSocketRecv = MockSocket.return_value.recv
        # reboot will do two sets, each followed by a get, so mock
        # the responses it would receive from the relay board
        MockSocketRecv.side_effect = [relay.COMMAND_OK,
                                      chr(1),
                                      relay.COMMAND_OK,
                                      chr(0)]
        r = self.app.post("/api/board/board1/reboot/")
        self.assertEqual(200, r.status)
        # Nothing in the response body currently
        self.assertEqual("relay-1",
                         MockSocket.return_value.connect.call_args[0][0][0])
        self.assertEqual(4, MockSocketRecv.call_count)

        # Verify that it got put into the rebooting state
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("rebooting", body["status"])

class TestBoardRedirects(ConfigMixin, unittest.TestCase):
    """
    The /boot/ and /reboot/ commands should 302 redirect to the
    correct server if the current server isn't the server that
    controls the board in question.
    """
    def setUp(self):
        super(TestBoardRedirects, self).setUp()
        add_server("server1")
        add_server("server2")
        add_board("board1", server="server1")
        add_board("board2", server="server2")
        add_bootimage("image1")

    def testRedirectBoard(self):
        r = self.app.post("/api/board/board2/reboot/")
        self.assertEqual(302, r.status)
        self.assertEqual("http://server2/api/board/board2/reboot/",
                         r.header("Location"))

        r = self.app.post("/api/board/board2/boot/image1/")
        self.assertEqual(302, r.status)
        self.assertEqual("http://server2/api/board/board2/boot/image1/",
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
        self.panda1_db['status'] = 'new'

        self.panda2_inv = dict(
            name='panda-0002',
            fqdn='panda-0002.r402-4.scl3.mozilla.com',
            inventory_id=202,
            mac_address='112233445566',
            imaging_server='mobile-services2',
            relay_info="relay-1:bank2:relay2")
        self.panda2_db = self.panda2_inv.copy()
        self.panda2_db['id'] = 402
        self.panda2_db['status'] = 'old'

    def test_merge_boards_no_change(self):
        commands = list(inventorysync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [])

    def test_merge_boards_insert(self):
        commands = list(inventorysync.merge_boards(
            [self.panda1_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [
            ('insert', self.panda2_inv),
        ])

    def test_merge_boards_delete(self):
        commands = list(inventorysync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', 401, self.panda1_db),
        ])

    def test_merge_boards_update(self):
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(inventorysync.merge_boards(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('update', 402, self.panda2_inv),
        ])

    def test_merge_boards_combo(self):
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(inventorysync.merge_boards(
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

    def make_host(self, name, want_mac_address=True, want_imaging_server=True, want_relay_info=True):
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
        return dict(
            hostname=fqdn,
            id=inventory_id,
            key_value=kv)

    def test_one_response(self, get):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002') ],
        ])
        hosts = list(inventorysync.get_boards('https://inv', 'filter', 'me', 'pass'))
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com'},
            {'inventory_id': 97, 'relay_info': 'relay9', 'name': 'panda-002',
             'imaging_server': 'img1', 'mac_address': '86a1c8ce6ea2',
             'fqdn': 'panda-002.vlan.dc.mozilla.com'},
        ])
        self.assertEqual(requests.get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
        ])

    maxDiff=None
    def test_loop_and_filtering(self, get):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002', want_imaging_server=False) ],
            [ self.make_host('panda-003'), self.make_host('panda-004', want_relay_info=False) ],
            [ self.make_host('panda-005'), self.make_host('panda-006', want_mac_address=False) ],
        ])
        hosts = inventorysync.get_boards('https://inv', 'filter', 'me', 'pass')
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
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
            mock.call('https://inv/path1', auth=('me', 'pass')),
            mock.call('https://inv/path2', auth=('me', 'pass')),
        ])

@patch('mozpool.db.data.dump_boards')
@patch('mozpool.db.data.insert_board')
@patch('mozpool.db.data.update_board')
@patch('mozpool.db.data.delete_board')
@patch('mozpool.lifeguard.inventorysync.get_boards')
@patch('mozpool.lifeguard.inventorysync.merge_boards')
class TestInvSyncSync(unittest.TestCase):

    def test_sync(self, merge_boards, get_boards, delete_board,
                        update_board, insert_board, dump_boards):
        config.reset()
        config.set('inventory', 'url', 'http://foo/')
        config.set('inventory', 'filter', 'hostname__startswith=panda-')
        config.set('inventory', 'username', 'u')
        config.set('inventory', 'password', 'p')
        dump_boards.return_value = 'dumped boards'
        get_boards.return_value = 'gotten boards'
        merge_boards.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        inventorysync.sync()
        dump_boards.assert_called_with()
        get_boards.assert_called_with('http://foo/', 'hostname__startswith=panda-', 'u', 'p', verbose=False)
        merge_boards.assert_called_with('dumped boards', 'gotten boards')
        insert_board.assert_called_with(dict(insert=1))
        delete_board.assert_called_with(10)
        update_board.assert_called_with(11, dict(update=3))


class StateMachineSubclass(statemachine.StateMachine):

    _counters = {}
    _state_name = 'state1'

    def read_state(self):
        return self._state_name

    def write_state(self, new_state, new_timeout_duration):
        self._state_name = new_state
        self._state_timeout_dur = new_timeout_duration

    def read_counters(self):
        return self._counters.copy()

    def write_counters(self, counters):
        self._counters = counters.copy()


@StateMachineSubclass.state_class
class state1(statemachine.State):

    on_poke_called = False
    on_timeout_called = False

    @statemachine.event_method('poke')
    def on_poke(self):
        state1.on_poke_called = True

    @statemachine.event_method('goto2')
    def on_goto2(self):
        self.machine.goto_state('state2')

    @statemachine.event_method('goto2_class')
    def on_goto2_class(self):
        self.machine.goto_state(state2)

    @statemachine.event_method('inc')
    def on_inc(self):
        self.machine.increment_counter('x')

    @statemachine.event_method('clear')
    def on_clear(self):
        self.machine.clear_counter('x')

    @statemachine.event_method('clear_all')
    def on_clear_all(self):
        self.machine.clear_counter()

    @statemachine.timeout_method(10)
    def on_timeout(self):
        state1.on_timeout_called = True


@StateMachineSubclass.state_class
class state2(statemachine.State):

    @statemachine.timeout_method(20)
    def on_timeout(self):
        pass


class TestStateSubclasses(unittest.TestCase):

    def setUp(self):
        self.machine = StateMachineSubclass('machine')

    def test_event(self):
        state1.on_poke_called = False
        self.machine.handle_event('poke')
        self.assertTrue(state1.on_poke_called)

    def test_unknown_event(self):
        self.machine.handle_event('never-heard-of-it')
        # TODO: assert logged

    def test_timeout(self):
        state1.on_timeout_called = False
        self.machine.handle_timeout()
        self.assertTrue(state1.on_timeout_called)

    def test_state_transition(self):
        # also tests on_exit and on_entry
        with mock.patch.object(state1, 'on_exit') as on_exit:
            with mock.patch.object(state2, 'on_entry') as on_entry:
                self.machine.handle_event('goto2')
                on_exit.assert_called()
                on_entry.assert_called()
        self.assertEqual(self.machine._state_name, 'state2')
        self.assertEqual(self.machine._state_timeout_dur, 20)

    def test_state_transition_class_name(self):
        self.machine.handle_event('goto2_class')
        self.assertEqual(self.machine._state_name, 'state2')
        self.assertEqual(self.machine._state_timeout_dur, 20)

    def test_increment_counter(self):
        self.machine.handle_event('inc')
        self.machine.handle_event('inc')
        self.assertEqual(self.machine._counters['x'], 2)

    def test_clear_counter_not_set(self):
        self.machine.handle_event('clear')
        self.assertFalse('x' in self.machine._counters)

    def test_clear_counter_set(self):
        self.machine._counters = dict(x=10)
        self.machine.handle_event('clear')
        self.assertFalse('x' in self.machine._counters)

    def test_clear_counter_all(self):
        self.machine._counters = dict(x=10, y=20)
        self.machine.handle_event('clear_all')
        self.assertEqual(self.machine._counters, {})

class TestLocksByName(unittest.TestCase):

    def setUp(self):
        self.lbn = util.LocksByName()

    def test_different_names(self):
        # this just needs to not deadlock..
        self.lbn.acquire('one')
        self.lbn.acquire('two')
        self.lbn.release('one')
        self.lbn.release('two')

    def test_same_name(self):
        events = []
        self.lbn.acquire('one')
        events.append('this locked')
        def other_thread():
            events.append('other started')
            self.lbn.acquire('one')
            events.append('other locked')
            self.lbn.release('one')
            events.append('other unlocked')
        thd = threading.Thread(target=other_thread)
        thd.start()
        # busywait for the thread to start
        while 'other started' not in events:
            pass
        events.append('unlocking this')
        self.lbn.release('one')
        thd.join()

        self.assertEqual(events,
            [ 'this locked', 'other started', 'unlocking this', 'other locked', 'other unlocked' ])

if __name__ == "__main__":
    unittest.main()
