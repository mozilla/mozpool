#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import sys
import unittest
import json
import socket
import tempfile
from mock import patch
from paste.fixture import TestApp

sys.path.append(os.path.join(os.getcwd(), "server"))

from bmm import server
from bmm import data
from bmm import relay
from bmm import testing
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
        self.assertEquals({"abc": "xyz"}, body["config"])

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

if __name__ == "__main__":
    unittest.main()
