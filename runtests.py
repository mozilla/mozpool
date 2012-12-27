#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import sys
import unittest
import json
import hashlib
import shutil
import requests
import tempfile
import mock
import datetime
import threading
import urlparse
import logging
import cStringIO
import sqlalchemy
from mock import patch
from paste.fixture import TestApp

from mozpool import config
from mozpool import statemachine
from mozpool import util
from mozpool.web import server
from mozpool.db import data, sql
from mozpool.db import model
from mozpool.bmm import relay
from mozpool.bmm import pxe
from mozpool.bmm import ping
from mozpool.bmm import scripts
from mozpool.lifeguard import inventorysync
from mozpool.test.util import (add_server, add_hardware_type, add_device,
    add_pxe_config, add_image, add_image_pxe_config, add_request, setup_db)
from mozpool.test import fakerelay
import mozpool.bmm.api
import mozpool.lifeguard
from mozpool.lifeguard import devicemachine
from mozpool.mozpool import requestmachine

# like dict(), but with unicode keys
def udict(**elts):
    return dict((unicode(k), unicode(v) if isinstance(v, str) else v) for k, v in elts.iteritems())

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
        sql.get_conn().close()
        sql.engine = None
        shutil.rmtree(self.tempdir)

class TestData(ConfigMixin, unittest.TestCase):
    maxDiff = None

    def setUp(self):
        super(TestData, self).setUp()
        add_server("server1")
        add_hardware_type("panda", "ES Rev B2")
        add_device("device1", server="server1", relayinfo="relay-1:bank1:relay1")

    def testInsertHardwareType(self):
        add_hardware_type("phone", "samsung_galaxy_s2")
        self.assertRaises(sqlalchemy.exc.SQLAlchemyError,
                          lambda: add_hardware_type("phone",
                                                    "samsung_galaxy_s2"))

    def testRelayInfo(self):
        self.assertEquals(("relay-1", 1, 1),
                          data.device_relay_info("device1"))

    def testListDevices(self):
        self.assertEquals(data.list_devices(), { 'devices' : [ 'device1' ] })

    def testListDevicesDetails(self):
        add_image('img1', id=23)
        add_device('device2', last_image_id=23, server='server1')
        self.assertEquals(data.list_devices(detail=True), {'devices': [
            udict(id=1, name='device1', fqdn='device1', inventory_id=1,
                  mac_address='000000000000', imaging_server='server1',
                  relay_info='relay-1:bank1:relay1', state='offline',
                  comments=None, last_image=None, boot_config=u'{}',
                  environment=None),
            udict(id=2, name='device2', fqdn='device2', inventory_id=2,
                  mac_address='000000000000', imaging_server='server1',
                  relay_info='', state='offline', comments=None,
                  last_image='img1', boot_config=u'{}', environment=None),
            ]})

    def testDumpDevices(self):
        self.assertEquals(data.dump_devices(), [
            dict(id=1, name='device1', fqdn='device1', inventory_id=1, mac_address='000000000000',
                imaging_server='server1', relay_info='relay-1:bank1:relay1'),
            ])

    def testAllDeviceStates(self):
        add_device('device2', server='server1', state='foobared')
        self.assertEquals(data.all_device_states(), { 'device1' : 'offline', 'device2' : 'foobared' })

    def testInsertDevice(self):
        data.insert_device(dict(
                name='device2', fqdn='device2.fqdn', inventory_id=23,
                mac_address='aabbccddeeff', imaging_server='server2',
                relay_info='relay-2:bank2:relay2',
                hardware_type='panda', hardware_model='ES Rev B2'))
        # device with existing imaging_server to test the insert-if-not-found behavior
        data.insert_device(dict(
                name='device3', fqdn='device3.fqdn', inventory_id=24,
                mac_address='aabbccddeeff', imaging_server='server1',
                relay_info='relay-2:bank2:relay2',
                hardware_type='panda', hardware_model='ES Rev B2'))
        conn = sql.get_conn()
        res = conn.execute(model.devices.select())
        self.assertEquals(sorted([ dict(r) for r in res.fetchall() ]),
        sorted([
            {u'state': u'new', u'state_counters': u'{}', u'state_timeout': None,
             u'relay_info': u'relay-2:bank2:relay2', u'name': u'device2',
             u'fqdn': u'device2.fqdn', u'inventory_id': 23,
             u'imaging_server_id': 2, u'boot_config': None,
             u'mac_address': u'aabbccddeeff', u'id': 2, u'last_image_id': None,
             u'comments': None, u'environment': None, u'hardware_type_id': 1},
            {u'state': u'new',u'state_counters': u'{}', u'state_timeout': None,
             u'relay_info': u'relay-2:bank2:relay2', u'name': u'device3',
             u'fqdn': u'device3.fqdn', u'inventory_id': 24,
             u'imaging_server_id': 1, u'boot_config': None,
             u'mac_address': u'aabbccddeeff', u'id': 3, u'last_image_id': None,
             u'comments': None, u'environment': None, u'hardware_type_id': 1},
            {u'state': u'offline',u'state_counters': u'{}', u'state_timeout': None,
             u'relay_info': u'relay-1:bank1:relay1', u'name': u'device1',
             u'fqdn': u'device1', u'inventory_id': 1, u'imaging_server_id': 1,
             u'boot_config': u'{}', u'mac_address': u'000000000000', u'id': 1,
             u'last_image_id': None, u'comments': None, u'environment': None,
             u'hardware_type_id': 1},
            ]))

    def testDeleteDevice(self):
        conn = sql.get_conn()
        now = datetime.datetime.now()
        add_device("device2", server="server1", relayinfo="relay-2:bank1:relay1")
        conn.execute(model.device_logs.insert(), [
            dict(device_id=1, ts=now, source='test', message='hi'),
            dict(device_id=1, ts=now, source='test', message='world'),
        ])
        data.delete_device(1)

        # check that both logs and devices were deleted
        res = conn.execute(sqlalchemy.select([model.devices.c.name]))
        self.assertEquals(res.fetchall(), [('device2',)])
        res = conn.execute(model.device_logs.select())
        self.assertEquals(res.fetchall(), [])

    def testUpdateDevice(self):
        conn = sql.get_conn()
        data.update_device(1, dict(fqdn='device1.fqdn', imaging_server='server9', mac_address='aabbccddeeff'))
        res = conn.execute(model.devices.select())
        self.assertEquals([ dict(r) for r in res.fetchall() ], [
            {u'state': u'offline', u'state_counters': u'{}', u'state_timeout': None,
             u'relay_info': u'relay-1:bank1:relay1', u'name': u'device1',
             u'fqdn': u'device1.fqdn', u'inventory_id': 1, u'imaging_server_id': 2,
             u'boot_config': u'{}', u'mac_address': u'aabbccddeeff', u'id': 1,
             u'last_image_id': None, u'comments': None, u'environment': None,
             u'hardware_type_id': 1},
        ])

    def testDeviceConfigEmpty(self):
        self.assertEqual(data.device_config('foo'), {})

    def testDeviceConfigNoImage(self):
        add_device("withconfig", server="server1", config='abcd')
        self.assertEqual(data.device_config('withconfig'),
                         {'boot_config': 'abcd', 'image': None})

    def testDeviceConfigImage(self):
        add_image('img1', id=23)
        add_device("withimg", config='', server="server1", last_image_id=23)
        self.assertEqual(data.device_config('withimg'),
                         {'boot_config': '', 'image': 'img1'})

    def test_get_free_devices(self):
        # (note, device1 is not free)
        add_server('server')
        add_image('img1', id=23)
        add_device("device2", state='free', environment='foo')
        add_device("device3", state='free', environment='bar')
        # device4 has an outstanding request that's still open, even
        # though its state is free; it should not be returned
        add_device("device4", state='free', environment='bar')
        add_request('server', device='device4', image='img1')
        self.assertEqual(sorted(data.get_free_devices()),
                         sorted(['device2', 'device3']))
        self.assertEqual(sorted(data.get_free_devices(environment='foo')),
                         sorted(['device2']))
        self.assertEqual(sorted(data.get_free_devices(environment='bar')),
                         sorted(['device3']))
        self.assertEqual(sorted(data.get_free_devices(environment='bing')),
                         sorted([]))
        self.assertEqual(sorted(data.get_free_devices(
                         environment='bar', device_name='device2')),
                         sorted([]))
        self.assertEqual(sorted(data.get_free_devices(
                         environment='bar', device_name='device3')),
                         sorted(['device3']))


class TestDeviceList(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestDeviceList, self).setUp()
        add_server("server1")
        add_device("device1", server="server1")
        add_device("device2", server="server1")
        add_server("server2")
        add_device("device3", server="server2")
        add_device("device4", server="server2")

    def testDeviceList(self):
        """
        /device/list/ should list all devices for all servers.
        """
        r = self.app.get("/api/device/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("devices" in body)
        self.assertTrue("device1" in body["devices"])
        self.assertTrue("device2" in body["devices"])
        self.assertTrue("device3" in body["devices"])
        self.assertTrue("device4" in body["devices"])

        r = self.app.get("/api/device/list/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertTrue("devices" in body)
        self.assertTrue("device1" in body["devices"])
        self.assertTrue("device2" in body["devices"])
        self.assertTrue("device3" in body["devices"])
        self.assertTrue("device4" in body["devices"])

class TestDeviceStatus(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestDeviceStatus, self).setUp()
        add_server("server1")
        add_device("device1", server="server1", state="running")
        add_device("device2", server="server1", state="freaking_out")
        add_server("server2")
        add_device("device3", server="server2", state="running")

    def testDeviceState(self):
        """
        /device/{id}/state/ should return the state.
        """
        r = self.app.get("/api/device/device1/state/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals({'state': 'running'}, body)

        r = self.app.get("/api/device/device2/state/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals({'state': 'freaking_out'}, body)

    def testDeviceStatus(self):
        """
        /device/{id}/status/ should work for any device on any server.
        """
        r = self.app.get("/api/device/device1/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["state"])

        r = self.app.get("/api/device/device2/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("freaking_out", body["state"])

        r = self.app.get("/api/device/device3/status/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEquals("running", body["state"])

class TestDeviceConfig(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestDeviceConfig, self).setUp()
        add_server("server1")
        add_pxe_config('img1', contents='IMG1 ip=%IPADDRESS%')

    def testDeviceConfig(self):
        boot_config={'b2gbase':'BBB'}
        add_device("device1", server="server1", config=json.dumps(boot_config))
        r = self.app.get("/api/device/device1/bootconfig/")
        self.assertEqual(200, r.status)
        self.assertEquals(boot_config, json.loads(r.body))

class TestRequests(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestRequests, self).setUp()
        add_pxe_config('b2gimage1')
        add_image('b2g', '["b2gbase"]')
        add_hardware_type('model', 'ES Rev B2')
        add_image_pxe_config('b2g', 'b2gimage1', 'model', 'ES Rev B2')
        add_server("server1")
        add_server("server2")
        add_device("device1", server="server1", state="free")
        add_device("device2", server="server1", state="free")
        add_device("device3", server="server1", state="ready")
        add_request("server2", device="device3", state="ready")
        mozpool.mozpool.driver = requestmachine.MozpoolDriver()

    def testRequestDevice(self):
        # asserts related to IDs are mostly to identify them for debugging

        # test bad requests
        # no image
        request_params = {"assignee": "slave1",
                          "duration": 3600}
        r = self.app.post("/api/device/device1/request/",
                          json.dumps(request_params), expect_errors=True)
        self.assertEqual(400, r.status)
        # no b2gbase for b2g image
        request_params["image"] = "b2g"
        r = self.app.post("/api/device/device1/request/",
                          json.dumps(request_params), expect_errors=True)
        self.assertEqual(400, r.status)

        request_params["b2gbase"] = "http://fakebuildserver/fakebuild/"
        r = self.app.post("/api/device/device1/request/",
                          json.dumps(request_params))
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEqual(body["request"]["id"], 2)
        self.assertEqual(body["request"]["assigned_device"], "device1")
        self.assertEqual(urlparse.urlparse(body["request"]["url"]).path,
                         "/api/request/2/")
        r = self.app.post("/api/device/device1/request/",
                          json.dumps(request_params), expect_errors=True)
        self.assertEqual(409, r.status)
        body = json.loads(r.body)
        self.assertEqual(body["request"]["id"], 3)
        self.assertEqual(body["request"]["assigned_device"], "")

        # test "any" request
        r = self.app.post("/api/device/any/request/",
                          json.dumps(request_params))
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        device2_request_id = body["request"]["id"]
        self.assertEqual(device2_request_id, 4)
        self.assertEqual(body["request"]["assigned_device"], "device2")
        r = self.app.post("/api/device/any/request/",
                          json.dumps(request_params))
        # it will retry a few times to find a device, so we'll get back
        # a 200 error but no assigned device
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEqual(body["request"]["id"], 5)
        self.assertEqual(body["request"]["assigned_device"], "")

        # test details for found and not found devices
        r = self.app.get("/api/request/10/details/", expect_errors=True)
        self.assertEqual(404, r.status)
        r = self.app.get("/api/request/3/details/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertGreater(body["expires"],
                           datetime.datetime.utcnow().isoformat())
        self.assertLessEqual(body["expires"], (datetime.datetime.utcnow() +
                             datetime.timedelta(seconds=3600)).isoformat())

        # test renew
        r = self.app.post("/api/request/3/renew/",
                          json.dumps({"duration": 360}))
        self.assertEqual(204, r.status)
        r = self.app.get("/api/request/3/details/")
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertGreater(body["expires"],
                           datetime.datetime.utcnow().isoformat())
        self.assertLessEqual(body["expires"], (datetime.datetime.utcnow() +
                             datetime.timedelta(seconds=360)).isoformat())

        # test redirects
        r = self.app.post("/api/request/1/renew/",
                          json.dumps({"duration": 360}))
        self.assertEqual(302, r.status)
        r = self.app.post("/api/request/1/return/")
        self.assertEqual(302, r.status)

        # test return
        r = self.app.post("/api/request/%d/return/" % device2_request_id)
        self.assertEqual(204, r.status)
        r = self.app.get("/api/device/device2/status/")
        body = json.loads(r.body)
        self.assertEqual(body["state"], "free")
        r = self.app.post("/api/device/device2/request/",
                          json.dumps(request_params))
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEqual(body["request"]["id"], 6)
        self.assertEqual(body["request"]["assigned_device"], "device2")

        # test busy device
        add_device("device4", server="server1", state="pxe_booting")
        r = self.app.post("/api/device/any/request/",
                          json.dumps(request_params), expect_errors=True)
        self.assertEqual(200, r.status)
        body = json.loads(r.body)
        self.assertEqual(body["request"]["id"], 7)
        self.assertEqual(body["request"]["assigned_device"], "")

        # test request list
        r = self.app.get("/api/request/list/")
        body = json.loads(r.body)
        self.assertEqual(len(body["requests"]), 5)
        r = self.app.get("/api/request/list/?include_closed=1")
        body = json.loads(r.body)
        self.assertEqual(len(body["requests"]), 7)

class TestDevicePowerCycle(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestDevicePowerCycle, self).setUp()
        add_server("server1")
        self.device_mac = "001122334455"
        add_device("device1", server="server1", state="running",
                  mac_address=self.device_mac,
                  relayinfo="relay-1:bank1:relay1")
        self.pxefile = "image1"
        # create a file for the boot image.
        open(os.path.join(config.get('paths', 'image_store'), self.pxefile), "w").write("abc")
        add_pxe_config("image1")

    @patch("mozpool.bmm.api.start_powercycle")
    @patch("mozpool.bmm.api.set_pxe")
    def testDevicePowerCycle(self, set_pxe, start_powercycle):
        body = {"pxe_config":"image1", "boot_config":"abcd"}
        r = self.app.post("/api/device/device1/power-cycle/",
                          headers={"Content-Type": "application/json"},
                          params=json.dumps(body))
        self.assertEqual(200, r.status)
        # Nothing in the response body currently
        set_pxe.assert_called_with('device1', 'image1', 'abcd')
        start_powercycle.assert_called_with('device1', mock.ANY)

class TestDevicePing(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestDevicePing, self).setUp()
        add_server("server1")
        self.device_mac = "001122334455"
        add_device("device1", server="server1", state="running",
                  mac_address=self.device_mac,
                  relayinfo="relay-1:bank1:relay1")
        self.pxefile = "image1"
        # create a file for the boot image.
        open(os.path.join(config.get('paths', 'image_store'), self.pxefile), "w").write("abc")
        add_pxe_config("image1")

    @patch("mozpool.bmm.api.ping")
    def testDevicePing(self, ping):
        ping.return_value = True
        r = self.app.get("/api/device/device1/ping/")
        self.assertEqual(200, r.status)
        self.assertEqual(json.loads(r.body), {'success':True})

class TestDeviceStateChange(ConfigMixin, unittest.TestCase):
    def setUp(self):
        super(TestDeviceStateChange, self).setUp()
        mozpool.lifeguard.driver = devicemachine.LifeguardDriver()
        add_device("device1", server="server1", state="ready",
                  relayinfo="relay-1:bank1:relay1")

    @patch('mozpool.bmm.api.clear_pxe')
    @patch('mozpool.statemachine.StateMachine.goto_state')
    def testStateChange(self, goto_state, clear_pxe):
        r = self.app.post("/api/device/device1/state-change/ready/to/new/",
                params='{}')
        self.assertEqual(200, r.status)
        goto_state.assert_called_with('new')
        clear_pxe.assert_called_with('device1')

    @patch('mozpool.bmm.api.set_pxe')
    @patch('mozpool.statemachine.StateMachine.goto_state')
    def testStateChangeWithPxe(self, goto_state, set_pxe):
        r = self.app.post("/api/device/device1/state-change/ready/to/new/",
                params=json.dumps(dict(pxe_config='p', boot_config='b')))
        self.assertEqual(200, r.status)
        goto_state.assert_called_with('new')
        set_pxe.assert_called_with('device1', 'p', 'b')

    @patch('mozpool.statemachine.StateMachine.goto_state')
    def testStateChangeConflict(self, goto_state):
        # try changing from 'new', which doesn't exist
        r = self.app.post("/api/device/device1/state-change/new/to/pxe_rebooting/",
                params='{}', expect_errors=True)
        self.assertEqual(409, r.status)

class TestDeviceRedirects(ConfigMixin, unittest.TestCase):
    """
    Lifeguard commands should 302 redirect to the correct server if the current
    server isn't the server that controls the device in question.
    """
    def setUp(self):
        super(TestDeviceRedirects, self).setUp()
        add_server("server1")
        add_server("server2")
        add_device("device1", server="server1")
        add_device("device2", server="server2")
        add_pxe_config("image1")

    def testRedirectDevice(self):
        r = self.app.post("/api/device/device2/event/foo/")
        self.assertEqual(302, r.status)
        self.assertEqual("http://server2/api/device/device2/event/foo/",
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

    def test_merge_devices_no_change(self):
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [])

    def test_merge_devices_insert(self):
        commands = list(inventorysync.merge_devices(
            [self.panda1_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(commands, [
            ('insert', self.panda2_inv),
        ])

    def test_merge_devices_delete(self):
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('delete', 401, self.panda1_db),
        ])

    def test_merge_devices_update(self):
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(inventorysync.merge_devices(
            [self.panda1_db, self.panda2_db],
            [self.panda1_inv, self.panda2_inv]))
        self.assertEqual(sorted(commands), [
            ('update', 402, self.panda2_inv),
        ])

    def test_merge_devices_combo(self):
        self.panda2_inv['mac_address'] = '1a2b3c4d5e6f'
        commands = list(inventorysync.merge_devices(
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
        hosts = inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', None)
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com', 'hardware_type': 'panda',
             'hardware_model': 'ES Rev B2'},
            {'inventory_id': 97, 'relay_info': 'relay9', 'name': 'panda-002',
             'imaging_server': 'img1', 'mac_address': '86a1c8ce6ea2',
             'fqdn': 'panda-002.vlan.dc.mozilla.com', 'hardware_type': 'panda',
             'hardware_model': 'ES Rev B2'},
        ])
        self.assertEqual(requests.get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
        ])

    def test_re_filter(self, get):
        self.set_responses([
            [ self.make_host('panda-001'), self.make_host('panda-002') ],
        ])
        hosts = inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', '.*9')
        self.assertEqual(hosts, [
            # panda-001 was skipped, since 'img9' matches '.*9'
            {'inventory_id': 97, 'relay_info': 'relay9', 'name': 'panda-002',
             'imaging_server': 'img1', 'mac_address': '86a1c8ce6ea2',
             'fqdn': 'panda-002.vlan.dc.mozilla.com', 'hardware_type': 'panda',
             'hardware_model': 'ES Rev B2'},
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
        hosts = inventorysync.get_devices('https://inv', 'filter', 'me', 'pass', None)
        self.assertEqual(hosts, [
            {'inventory_id': 90, 'relay_info': 'relay7', 'name': 'panda-001',
             'imaging_server': 'img9', 'mac_address': '6a3d0c52ae9b',
             'fqdn': 'panda-001.vlan.dc.mozilla.com', 'hardware_type': 'panda',
             'hardware_model': 'ES Rev B2'},
            # panda-002 was skipped
            {'inventory_id': 52, 'relay_info': 'relay4', 'name': 'panda-003',
             'imaging_server': 'img9', 'mac_address': 'aec31326594a',
             'fqdn': 'panda-003.vlan.dc.mozilla.com', 'hardware_type': 'panda',
             'hardware_model': 'ES Rev B2'},
            # panda-004 was skipped
            {'inventory_id': 6, 'relay_info': 'relay9', 'name': 'panda-005',
             'imaging_server': 'img3', 'mac_address': 'c19b00f9644b',
             'fqdn': 'panda-005.vlan.dc.mozilla.com', 'hardware_type': 'panda',
             'hardware_model': 'ES Rev B2'}
            # panda-006 was skipped
        ])
        self.assertEqual(requests.get.call_args_list, [
            mock.call('https://inv/en-US/tasty/v3/system/?limit=100&filter', auth=('me', 'pass')),
            mock.call('https://inv/path1', auth=('me', 'pass')),
            mock.call('https://inv/path2', auth=('me', 'pass')),
        ])

@patch('mozpool.db.data.dump_devices')
@patch('mozpool.db.data.insert_device')
@patch('mozpool.db.data.update_device')
@patch('mozpool.db.data.delete_device')
@patch('mozpool.lifeguard.inventorysync.get_devices')
@patch('mozpool.lifeguard.inventorysync.merge_devices')
class TestInvSyncSync(unittest.TestCase):

    def test_sync(self, merge_devices, get_devices, delete_device,
                        update_device, insert_device, dump_devices):
        config.reset()
        config.set('inventory', 'url', 'http://foo/')
        config.set('inventory', 'filter', 'hostname__startswith=panda-')
        config.set('inventory', 'username', 'u')
        config.set('inventory', 'password', 'p')
        dump_devices.return_value = 'dumped devices'
        get_devices.return_value = 'gotten devices'
        merge_devices.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        inventorysync.sync()
        dump_devices.assert_called_with()
        get_devices.assert_called_with('http://foo/', 'hostname__startswith=panda-', 'u', 'p', None,
                verbose=False)
        merge_devices.assert_called_with('dumped devices', 'gotten devices')
        insert_device.assert_called_with(dict(insert=1))
        delete_device.assert_called_with(10)
        update_device.assert_called_with(11, dict(update=3))

    def test_sync_with_res(self, merge_devices, get_devices, delete_device,
                        update_device, insert_device, dump_devices):
        config.reset()
        config.set('inventory', 'url', 'http://foo/')
        config.set('inventory', 'filter', 'hostname__startswith=panda-')
        config.set('inventory', 'username', 'u')
        config.set('inventory', 'password', 'p')
        config.set('inventory', 'ignore_devices_on_servers_re', 're')
        dump_devices.return_value = 'dumped devices'
        get_devices.return_value = 'gotten devices'
        merge_devices.return_value = [
            ('insert', dict(insert=1)),
            ('delete', 10, dict(delete=2)),
            ('update', 11, dict(update=3)),
        ]
        inventorysync.sync()
        dump_devices.assert_called_with()
        get_devices.assert_called_with('http://foo/', 'hostname__startswith=panda-', 'u', 'p', 're',
                verbose=False)
        merge_devices.assert_called_with('dumped devices', 'gotten devices')
        insert_device.assert_called_with(dict(insert=1))
        delete_device.assert_called_with(10)
        update_device.assert_called_with(11, dict(update=3))


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

    TIMEOUT = 10

    called_on_poke = False
    called_on_timeout = False

    def on_poke(self, args):
        state1.called_on_poke = True

    def on_goto2(self, args):
        self.machine.goto_state('state2')

    def on_goto2_class(self, args):
        self.machine.goto_state(state2)

    def on_inc(self, args):
        self.machine.increment_counter('x')

    def on_clear(self, args):
        self.machine.clear_counter('x')

    def on_clear_all(self, args):
        self.machine.clear_counter()

    def on_timeout(self):
        state1.called_on_timeout = True


@StateMachineSubclass.state_class
class state2(statemachine.State):

    TIMEOUT = 20

    def on_timeout(self):
        pass

# test that different state machines can have states with the same names; this
# just introduces an extra state machine that ideally shouldn't interfere at
# all.
class Namespace: # so 'state1' doesn't get replaced in the module dict
    class StateMachineSubclass2(statemachine.StateMachine):
        pass
    @StateMachineSubclass2.state_class
    class state2(statemachine.State):
        pass


class TestStateSubclasses(unittest.TestCase):

    def setUp(self):
        self.machine = StateMachineSubclass('test', 'machine')

    def test_event(self):
        state1.called_on_poke = False
        self.machine.handle_event('poke', {})
        self.assertTrue(state1.called_on_poke)

    def test_unknown_event(self):
        self.machine.handle_event('never-heard-of-it', {})
        # TODO: assert logged

    def test_timeout(self):
        state1.called_on_timeout = False
        self.machine.handle_timeout()
        self.assertTrue(state1.called_on_timeout)

    def test_state_transition(self):
        # also tests on_exit and on_entry
        with mock.patch.object(state1, 'on_exit') as on_exit:
            with mock.patch.object(state2, 'on_entry') as on_entry:
                self.machine.handle_event('goto2', {})
                on_exit.assert_called()
                on_entry.assert_called()
        self.assertEqual(self.machine._state_name, 'state2')
        self.assertEqual(self.machine._state_timeout_dur, 20)

    def test_state_transition_class_name(self):
        self.machine.handle_event('goto2_class', {})
        self.assertEqual(self.machine._state_name, 'state2')
        self.assertEqual(self.machine._state_timeout_dur, 20)

    def test_increment_counter(self):
        self.machine.handle_event('inc', {})
        self.machine.handle_event('inc', {})
        self.assertEqual(self.machine._counters['x'], 2)

    def test_clear_counter_not_set(self):
        self.machine.handle_event('clear', {})
        self.assertFalse('x' in self.machine._counters)

    def test_clear_counter_set(self):
        self.machine._counters = dict(x=10)
        self.machine.handle_event('clear', {})
        self.assertFalse('x' in self.machine._counters)

    def test_clear_counter_all(self):
        self.machine._counters = dict(x=10, y=20)
        self.machine.handle_event('clear_all', {})
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

class TestBmmApi(unittest.TestCase):

    def wait_for_async(self, start_fn):
        done_cond = threading.Condition()

        cb_result = []
        def cb(arg):
            cb_result.append(arg)
            done_cond.acquire()
            done_cond.notify()
            done_cond.release()

        done_cond.acquire()
        start_fn(cb)
        done_cond.wait()
        done_cond.release()

        return cb_result[0]

    def do_call_start_powercycle(self, device_name, max_time):
        return self.wait_for_async(lambda cb :
            mozpool.bmm.api.start_powercycle(device_name, cb, max_time))

    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.relay.powercycle')
    @patch('mozpool.db.data.device_relay_info')
    def test_good(self, device_relay_info, powercycle, logs_add):
        device_relay_info.return_value = ('relay1', 1, 3)
        powercycle.return_value = True
        self.assertEqual(self.do_call_start_powercycle('dev1', max_time=30), True)
        device_relay_info.assert_called_with('dev1')
        powercycle.assert_called_with('relay1', 1, 3, 30)
        logs_add.assert_called()

    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.relay.powercycle')
    @patch('mozpool.db.data.device_relay_info')
    def test_bad(self, device_relay_info, powercycle, logs_add):
        device_relay_info.return_value = ('relay1', 1, 3)
        powercycle.return_value = False
        self.assertEqual(self.do_call_start_powercycle('dev1', max_time=30), False)
        logs_add.assert_called()

    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.relay.powercycle')
    @patch('mozpool.db.data.device_relay_info')
    def test_exceptions(self, device_relay_info, powercycle, logs_add):
        device_relay_info.return_value = ('relay1', 1, 3)
        powercycle.return_value = False
        powercycle.side_effect = lambda *args : 11/0 # ZeroDivisionError
        self.assertEqual(self.do_call_start_powercycle('dev1', max_time=0.01), False)
        logs_add.assert_called()

    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.pxe.set_pxe')
    def test_set_pxe(self, pxe_set_pxe, logs_add):
        mozpool.bmm.pxe.set_pxe('device1', 'img1', 'cfg')
        pxe_set_pxe.assert_called_with('device1', 'img1', 'cfg')
        logs_add.assert_called()

    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.pxe.clear_pxe')
    def test_clear_pxe(self, pxe_clear_pxe, logs_add):
        mozpool.bmm.pxe.clear_pxe('device1')
        pxe_clear_pxe.assert_called_with('device1')
        logs_add.assert_called()

    def do_call_start_ping(self, device_name):
        return self.wait_for_async(lambda cb :
            mozpool.bmm.api.start_ping(device_name, cb))

    @patch('mozpool.db.data.device_fqdn')
    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.ping.ping')
    def test_start_ping(self, ping, log_add, device_fqdn):
        ping.return_value = True
        device_fqdn.return_value = 'abcd'
        self.do_call_start_ping('xyz')
        device_fqdn.assert_called_with('xyz')
        log_add.assert_called()
        ping.assert_called_with('abcd')

    @patch('mozpool.db.data.device_fqdn')
    @patch('mozpool.db.logs.Logs.add')
    @patch('mozpool.bmm.ping.ping')
    def test_ping(self, ping, log_add, device_fqdn):
        ping.return_value = True
        device_fqdn.return_value = 'abcd'
        mozpool.bmm.api.ping('xyz')
        device_fqdn.assert_called_with('xyz')
        log_add.assert_called()
        ping.assert_called_with('abcd')


class TestBmmRelay(unittest.TestCase):

    def setUp(self):
        # start up a fake relay server, and set relay.PORT to point to it
        self.relayboard = fakerelay.RelayBoard('test', ('127.0.0.1', 0), record_actions=True)
        self.relayboard.add_relay(2, 2, fakerelay.Relay())
        self.relayboard.spawn_one()
        self.relay_host = '127.0.0.1:%d' % self.relayboard.get_port()

    @patch('time.sleep')
    def test_get_status(self, sleep):
        self.assertEqual(relay.get_status(self.relay_host, 2, 2, 10), True)
        self.assertEqual(self.relayboard.actions, [('get', 2, 2)])

    def test_get_status_timeout(self):
        self.relayboard.delay = 1
        self.assertEqual(relay.get_status(self.relay_host, 2, 2, 0.1), None)

    @patch('time.sleep')
    def test_set_status_on(self, sleep):
        self.assertEqual(relay.set_status(self.relay_host, 2, 2, True, 10), True)
        self.assertEqual(self.relayboard.actions, [('set', 'panda-on', 2, 2)])

    @patch('time.sleep')
    def test_set_status_off(self, sleep):
        self.assertEqual(relay.set_status(self.relay_host, 2, 2, False, 10), True)
        self.assertEqual(self.relayboard.actions, [('set', 'panda-off', 2, 2)])

    def test_set_status_timeout(self):
        self.relayboard.delay = 1
        self.assertEqual(relay.set_status(self.relay_host, 2, 2, True, 0.1), False)

    @patch('time.sleep')
    def test_powercycle(self, sleep):
        self.assertEqual(relay.powercycle(self.relay_host, 2, 2, 10), True)
        self.assertEqual(self.relayboard.actions,
                [('set', 'panda-off', 2, 2), ('get', 2, 2), ('set', 'panda-on', 2, 2), ('get', 2, 2)])

    def test_powercycle_timeout(self):
        self.relayboard.delay = 0.05
        self.assertEqual(relay.powercycle(self.relay_host, 2, 2, 0.1), False)


class TestBmmPxe(ConfigMixin, unittest.TestCase):

    def setUp(self):
        super(TestBmmPxe, self).setUp()
        config.set('server', 'ipaddress', '1.2.3.4')
        add_server("server1")
        add_device("device1", server="server1", relayinfo="relay-1:bank1:relay1",
                            mac_address='aabbccddeeff')
        add_pxe_config('img1', contents='IMG1 ip=%IPADDRESS%')

    def test_set_pxe(self):
        pxe.set_pxe('device1', 'img1', 'config')
        cfg_filename = os.path.join(os.path.join(self.tempdir, 'tftp', 'pxelinux.cfg'), '01-aa-bb-cc-dd-ee-ff')
        self.assertEqual(open(cfg_filename).read(), 'IMG1 ip=1.2.3.4')

    def test_clear_pxe(self):
        cfg_dir = os.path.join(self.tempdir, 'tftp', 'pxelinux.cfg')
        cfg_filename = os.path.join(cfg_dir, '01-aa-bb-cc-dd-ee-ff')
        os.makedirs(cfg_dir)
        open(cfg_filename, "w").write("IMG2")
        pxe.clear_pxe('device1')
        self.assertFalse(os.path.exists(cfg_filename))

    def test_clear_pxe_nonexistent(self):
        # just has to not fail!
        pxe.clear_pxe('device1')

class TestBmmPing(unittest.TestCase):

    fixed_args = '-q -r4 -t50'

    @patch("os.system")
    def test_ping_success(self, system):
        system.return_value = 0
        self.assertTrue(ping.ping('abcd'))
        system.assert_called_with('fping %s abcd' % self.fixed_args)

    @patch("os.system")
    def test_ping_fails(self, system):
        system.return_value = 256
        self.assertFalse(ping.ping('abcd'))
        system.assert_called_with('fping %s abcd' % self.fixed_args)

class TestPxeConfigScript(ConfigMixin, unittest.TestCase):

    def setUp(self):
        super(TestPxeConfigScript, self).setUp()
        self.old_stderr, self.old_stdout = sys.stderr, sys.stdout
        sys.stderr = cStringIO.StringIO()
        sys.stdout = cStringIO.StringIO()

    def tearDown(self):
        sys.stderr = self.old_stderr
        sys.stdout = self.old_stdout
        if os.path.exists('test-config'):
            os.unlink('test-config')

    def assertStderr(self, expected):
        self.assertIn(expected, sys.stderr.getvalue())

    def assertStdout(self, expected):
        self.assertIn(expected, sys.stdout.getvalue())

    def write_config(self, config):
        open('test-config', 'w').write(config)

    # tests

    def test_empty(self):
        self.assertRaises(SystemExit, lambda :
            scripts.pxe_config_script([]))
        self.assertStderr('too few')

    def test_list_with_name(self):
        self.assertRaises(SystemExit, lambda :
            scripts.pxe_config_script(['list', 'device1']))
        self.assertStderr('name is not allowed')

    def test_show_without_name(self):
        self.assertRaises(SystemExit, lambda :
            scripts.pxe_config_script(['show']))
        self.assertStderr('name is required')

    def test_add(self):
        self.write_config('this is my config')
        scripts.pxe_config_script(['add', 'testy', '-m' 'TEST', '-c', 'test-config'])
        self.assertEqual(data.pxe_config_details('testy'),
                {'details':{'description':'TEST', 'contents':'this is my config',
                            'active':True, 'name':'testy'}})
        self.assertStdout('this is my')

    def test_modify(self):
        self.write_config('this is my config')
        add_pxe_config('testy')
        scripts.pxe_config_script(['modify', 'testy', '-m' 'TEST', '-c', 'test-config', '--inactive'])
        self.assertEqual(data.pxe_config_details('testy'),
                {'details':{'description':'TEST', 'contents':'this is my config',
                            'active':False, 'name':'testy'}})
        self.assertStdout('this is my')

    def test_show(self):
        add_pxe_config('testy', contents='abcd')
        scripts.pxe_config_script(['show', 'testy'])
        self.assertStdout('abcd')

    def test_list(self):
        add_pxe_config('testy1', contents='abcd')
        add_pxe_config('testy2', contents='hijk', active=False)
        scripts.pxe_config_script(['list' ])
        self.assertStdout('abcd')
        self.assertStdout('hijk')

if __name__ == "__main__":
    open("test.log", "w") # truncate the file
    logging.basicConfig(level=logging.DEBUG, filename='test.log')
    logger = logging.getLogger('runtests')

    # subclasses to print test names to the log
    class LoggingTextTestResult(unittest.TextTestResult):

        def startTest(self, test):
            logger.info("---- %s ----" % (self.getDescription(test),))
            super(LoggingTextTestResult, self).startTest(test)

    class LoggingTextTestRunner(unittest.TextTestRunner):
        resultclass = LoggingTextTestResult

    unittest.main(testRunner=LoggingTextTestRunner)
