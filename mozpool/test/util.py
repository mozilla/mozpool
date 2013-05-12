# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Functions for testing. Used by the unit tests, but also useful for
manual testing.
"""

import datetime
import shutil
import unittest
import tempfile
import json
import os
import sys
import mock
import cStringIO
from paste.fixture import TestApp
from sqlalchemy.sql import and_, select
from mozpool import config, db
from mozpool.db import model
from mozpool.db import exceptions
from mozpool.web import server

class TestCase(unittest.TestCase):
    """
    Parent class for TestCases; used as a replacement for unittest.TestCase.

    This class calls setUpMixin wherever that method is defined in parent
    classes, allowing easy use of the mixin classes below without a lot of
    setUp/tearDown boilerplate.  Setup occurs with parent classes first,
    while teardown occurs with child classes first.
    """

    def _enumerateMethods(self, name):
        seen = set()
        def iter(cls):
            if id(cls) in seen:
                return
            seen.add(id(cls))
            for base in cls.__bases__:
                for method in iter(base):
                    yield method
            unbound = cls.__dict__.get(name)
            if unbound:
                yield unbound.__get__(self, cls)
        return list(iter(self.__class__))

    def setUp(self):
        for setup in self._enumerateMethods('setUpMixin'):
            setup()

    def tearDown(self):
        for teardown in reversed(self._enumerateMethods('tearDownMixin')):
            teardown()

class ConfigMixin(object):
    """
    Clear the mozpool configuration and set a few defaults:
        server.fqdn = server1
        paths.tftp_root = $tempdir/tftp
    """

    def setUpMixin(self):
        config.reset()
        config.set('server', 'fqdn', 'my_fqdn')


class DirMixin(ConfigMixin):
    """
    Set up a temporary directory, `self.tempdir` and point paths.tftp_root into
    its `tftp` subdirectory.

    This mixin includes ConfigMixin.
    """
    def setUpMixin(self):
        self.tempdir = tempfile.mkdtemp()
        tftp_root = os.path.join(self.tempdir, "tftp")
        os.mkdir(tftp_root)
        config.set('paths', 'tftp_root', tftp_root)

    def tearDownMixin(self):
        shutil.rmtree(self.tempdir)


class DBMixin(DirMixin):
    """
    Set up a database instance at `self.db`.

    This class provides a number of additional helper functions to add test
    data to the database, as well.
    """

    def setUpMixin(self):
        # note that we can't use an in-memory DB, as that is not usable
        # from multiple threads.
        self.dbfile = os.path.join(self.tempdir, 'db.sqlite3')
        self.db = db.setup('sqlite:///' + self.dbfile)
        model.metadata.create_all(bind=self.db.pool.engine)

        # reset the local "fake" stuff
        self.inventory_id = 1

    # utility methods

    def add_server(self, hostname):
        """
        Configure data for a server running at |hostname|.
        """
        res = self.db.execute(model.imaging_servers.insert(), fqdn=hostname)
        return res.lastrowid

    def add_hardware_type(self, hw_type, hw_model):
        res = self.db.execute(model.hardware_types.insert(), type=hw_type,
                                    model=hw_model)
        return res.lastrowid

    def add_device(self, device, server="server", state="offline",
                mac_address="000000000000",
                image_id=None, boot_config=u'{}',
                next_image_id=None, next_boot_config=None,
                relayinfo="", hardware_type_id=1,
                environment=None, state_timeout=None,
                state_counters='{}'):
        id = self.db.execute(select([model.imaging_servers.c.id],
                                model.imaging_servers.c.fqdn==server)).fetchone()[0]
        if id is None:
            raise exceptions.NotFound
        res = self.db.execute(model.devices.insert(),
                    name=device,
                    fqdn=device + '.example.com', #XXX
                    inventory_id=self.inventory_id,
                    state=state,
                    state_counters=state_counters,
                    state_timeout=state_timeout,
                    mac_address=mac_address,
                    imaging_server_id=id,
                    relay_info=relayinfo,
                    image_id=image_id,
                    boot_config=boot_config,
                    next_image_id=next_image_id,
                    next_boot_config=next_boot_config,
                    hardware_type_id=hardware_type_id,
                    environment=environment)
        device_id = res.lastrowid
        self.inventory_id += 1
        return device_id

    def add_pxe_config(self, name, description="Boot image",
                    contents="BOOT THIS THINGIE WITH THIS CONFIG",
                    id=None, active=True):
        self.db.execute(model.pxe_configs.insert(), name=name,
                            description=description,
                            contents=contents,
                            id=id,
                            active=active)

    def add_image(self, name, boot_config_keys='[]', can_reuse=False, id=None,
                hidden=False, has_sut_agent=True):
        res = self.db.execute(model.images.insert(),
                            id=id,
                            name=name,
                            boot_config_keys=boot_config_keys,
                            can_reuse=can_reuse,
                            hidden=hidden,
                            has_sut_agent=has_sut_agent)
        return res.lastrowid

    def add_image_pxe_config(self, image_name, pxe_config_name, hardware_type,
                            hardware_model):
        image_id = self.db.execute(select(
                [model.images.c.id], model.images.c.name==image_name)).fetchone()[0]
        pxe_config_id = self.db.execute(select(
                [model.pxe_configs.c.id],
                model.pxe_configs.c.name==pxe_config_name)).fetchone()[0]
        hardware_type_id = self.db.execute(select(
                [model.hardware_types.c.id],
                and_(model.hardware_types.c.type==hardware_type,
                    model.hardware_types.c.model==hardware_model))).fetchone()[0]
        if image_id is None or pxe_config_id is None or hardware_type_id is None:
            raise exceptions.NotFound
        self.db.execute(model.image_pxe_configs.insert(),
                    image_id=image_id,
                    pxe_config_id=pxe_config_id,
                    hardware_type_id=hardware_type_id)

    def add_request(self, server='server', assignee="slave", state="new", expires=None,
                    device='any', image='b2g', boot_config='{}', no_assign=False):
        if not expires:
            expires = datetime.datetime.now() + datetime.timedelta(hours=1)
        image_id = self.db.execute(select([model.images.c.id],
                                    model.images.c.name==image)).fetchone()[0]
        if image_id is None:
            raise exceptions.NotFound
        server_id = self.db.execute(select([model.imaging_servers.c.id],
                                        model.imaging_servers.c.fqdn==server)).fetchone()[0]
        if server_id is None:
            raise exceptions.NotFound
        res = self.db.execute(model.requests.insert(),
                        imaging_server_id=server_id,
                        requested_device=device,
                        assignee=assignee,
                        expires=expires,
                        image_id=image_id,
                        boot_config=boot_config,
                        state=state,
                        state_counters='{}')
        request_id = res.lastrowid
        if device and state != 'closed' and not no_assign:
            self.add_device_request(request_id, device)
        return request_id

    def add_device_request(self, request_id, device):
        device_id = self.db.execute(select(
                [model.devices.c.id],
                model.devices.c.name==device)).fetchone()[0]
        self.db.execute(model.device_requests.insert(),
                    request_id=request_id,
                    device_id=device_id)

    def add_device_log(self, id, message, source, ts):
        self.db.execute(model.device_logs.insert(),
                device_id=id,
                message=message,
                source=source,
                ts=ts)

    def add_request_log(self, id, message, source, ts):
        self.db.execute(model.request_logs.insert(),
                request_id=id,
                message=message,
                source=source,
                ts=ts)

    def add_relay_board(self, relay_board, server="server", dn='.example.com',
                state="offline", state_timeout=None, state_counters='{}'):
        id = self.db.execute(select([model.imaging_servers.c.id],
                                model.imaging_servers.c.fqdn==server)).fetchone()[0]
        if id is None:
            raise exceptions.NotFound
        res = self.db.execute(model.relay_boards.insert(),
                    name=relay_board,
                    fqdn=relay_board + dn,
                    state=state,
                    state_counters=state_counters,
                    state_timeout=state_timeout,
                    imaging_server_id=id)
        return res.lastrowid


class ScriptMixin(object):
    """
    Set up to test scripts.  This provides a run_script method that will run a
    script method and catch SystemExit when the script finishes.
    """

    def run_script(self, method, argv):
        """
        Run script method `method` with command-line arguments `argv`.  Do not
        include sys.argv[0] here.  Returns the exit status
        """

        old_argv = sys.argv
        sys.argv = [ 'prog' ] + argv
        try:
            method()
        except SystemExit as e:
            return e.code
        finally:
            sys.argv = old_argv

class AppMixin(DBMixin):
    """
    Set up to test web stuff.  This sets up a db and creates a paste TestApp
    with the Mozpool web app, at `self.app`.  This also adds some utilities.
    """

    def setUpMixin(self):
        self.app = TestApp(server.get_app(self.db).wsgifunc())

    def post_json(self, url, body, **kwargs):
        return self.app.post(url, headers={"Content-Type": "application/json"},
                          params=json.dumps(body), **kwargs)

    def check_json_result(self, r):
        """Verify a JSON result and return the unserialized data."""
        self.assertEqual((200, 'application/json; charset=utf-8'),
                         (r.status, r.header('Content-Type')))
        return json.loads(r.body)

class PatchMixin(object):
    """
    Adds some useful extensions to mocking.

    The class variable 'auto_patch' is a list of (symbol, target, [kwargs])
    pairs.  The target will be patched, and the result assigned as an attribute
    of the testcase named symbol.  The kwargs, if present, are passed to
    mock.patch.
    """

    def setUpMixin(self):
        for elt in self.auto_patch:
            symbol, target = elt[:2]
            kwargs = elt[2] if len(elt) == 3 else {}
            p = mock.patch(target, **kwargs)
            setattr(self, symbol, p.start())
            self.addCleanup(p.stop)

    def reset_all_mocks(self):
        for elt in self.auto_patch:
            symbol = elt[0]
            patch = getattr(self, symbol)
            patch.reset_mock()

class StdioMixin(object):
    """
    Capture stdout and stderr during the test.
    """
    def setUpMixin(self):
        self.old_stderr, self.old_stdout = sys.stderr, sys.stdout
        sys.stderr = cStringIO.StringIO()
        sys.stdout = cStringIO.StringIO()

    def tearDownMixin(self):
        sys.stderr = self.old_stderr
        sys.stdout = self.old_stdout

    def assertStderr(self, expected):
        self.assertIn(expected, sys.stderr.getvalue())

    def assertStdout(self, expected):
        self.assertIn(expected, sys.stdout.getvalue())


class StateDriverMixin(DBMixin, ConfigMixin):
    """
    Support for doing integration tests of state machines.

    This sets up `self.driver` appropriately, based on self.driver_class.
    """

    driver_class = None

    def setUpMixin(self):
        # the driver looks up its server id in the constructor
        config.set('server', 'fqdn', 'server')
        self.add_server('server')

        self.driver = self.driver_class(self.db)

        # yuck, I hate this.  Anyway, set both to be sure.
        import mozpool.lifeguard
        import mozpool.mozpool
        mozpool.lifeguard.driver = self.driver
        mozpool.mozpool.driver = self.driver

    def tearDownMixin(self):
        self.driver.stop()
        import mozpool.lifeguard
        import mozpool.mozpool
        mozpool.lifeguard.driver = None
        mozpool.mozpool.driver = None
