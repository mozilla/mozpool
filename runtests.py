#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import sys
import unittest
import json
import shutil
import socket
import tempfile
from mock import patch
from paste.fixture import TestApp

from bmm import config
from bmm import server
from bmm import data
from bmm import relay
from bmm import testing
from bmm.testing import add_server, add_board, add_bootimage

class ConfigMixin(object):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.dbfile = os.path.join(self.tempdir, "sqlite.db")
        tftp_root = os.path.join(self.tempdir, "tftp")
        os.mkdir(tftp_root)
        image_store = os.path.join(self.tempdir, "images")
        os.mkdir(image_store)
        testing.set_config(sqlite_db=self.dbfile,
                           server_fqdn="server1",
                           tftp_root=tftp_root,
                           image_store=image_store,
                           create_db=True)
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

@patch("bmm.config.server_fqdn")
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
        """
        /board/list/ should list all boards for all servers.
        """
        Mock.return_value = "server1"
        r = self.app.get("/api/board/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("boards" in body)
        self.assertTrue("board1" in body["boards"])
        self.assertTrue("board2" in body["boards"])
        self.assertTrue("board3" in body["boards"])
        self.assertTrue("board4" in body["boards"])

        Mock.return_value = "server2"
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
        add_board("board1", server="server1", state="running")
        add_board("board2", server="server1", state="freaking_out")
        add_server("server2")
        add_board("board3", server="server2", state="running")

    def testBoardStatus(self):
        """
        /board/status/ should work for any board on any server.
        """
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["state"])

        r = self.app.get("/api/board/board2/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("freaking_out", body["state"])

        r = self.app.get("/api/board/board3/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["state"])

    def testSetBoardStatus(self):
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

class TestBoardConfig(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardConfig, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", config={"abc": "xyz"})

    def testBoardConfig(self):
        r = self.app.get("/api/board/board1/config/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals({"abc": "xyz"}, json.loads(body["config"]))

@patch("socket.socket")
class TestBoardBoot(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardBoot, self).setUp()
        add_server("server1")
        self.board_mac = "00:11:22:33:44:55"
        add_board("board1", server="server1", state="running",
                  mac_address=self.board_mac,
                  relayinfo="relay-1:bank1:relay1")
        self.pxefile = "image1"
        # create a file for the boot image.
        open(os.path.join(config.image_store(), self.pxefile), "w").write("abc")
        add_bootimage("image1", pxe_config_filename=self.pxefile)

    def testBoardBoot(self, MockSocket):
        MockSocketRecv = MockSocket.return_value.recv
        # reboot will do two sets, each followed by a get, so mock
        # the responses it would receive from the relay board
        mock_data = [relay.COMMAND_OK,
                     chr(1),
                     relay.COMMAND_OK,
                     chr(0)]
        self.done = False
        def mock_recv(*args):
            ret = mock_data.pop(0)
            if not mock_data:
                self.done = True
            return ret
        MockSocketRecv.side_effect = mock_recv
        r = self.app.post("/api/board/board1/boot/image1/")
        self.assertEqual(204, r.status)
        # Nothing in the response body currently

        # Verify that it got put into the boot-initiated state
        r = self.app.get("/api/board/board1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("boot-initiated", body["state"])

        # Verify that the symlink was created in tftp_root
        tftp_link = os.path.join(config.tftp_root(), self.board_mac)
        self.assertTrue(os.path.islink(tftp_link))

        # Verify that it links to the right PXE image.
        self.assertEqual(self.pxefile, os.path.basename(os.readlink(tftp_link)))

        #TODO: fake TFTP log for background thread to see.
        # Wait for the reboot command to complete in the background.
        while not self.done:
            pass

        self.assertNotEqual(None, MockSocket.return_value.connect.call_args)
        self.assertEqual("relay-1",
                         MockSocket.return_value.connect.call_args[0][0][0])

@patch("socket.socket")
class TestBoardReboot(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestBoardReboot, self).setUp()
        add_server("server1")
        add_board("board1", server="server1", state="running",
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

if __name__ == "__main__":
    unittest.main()
