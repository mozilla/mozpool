# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import os
from mozpool.test.util import TestCase, DirMixin, ScriptMixin, StdioMixin, DBMixin
from mozpool.bmm import scripts

class Tests(DBMixin, DirMixin, ScriptMixin, StdioMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.test_config_path = os.path.join(self.tempdir, 'test-config')
        scripts.setup = lambda : self.db

    def write_config(self, config):
        open(self.test_config_path, 'w').write(config)

    # relay script

    def test_relay_usage(self):
        self.assertEqual(self.run_script(
            scripts.relay_script, []),
            2)
        self.assertStdout('Usage:')

    def test_relay_bad_command(self):
        self.assertEqual(self.run_script(
            scripts.relay_script, [ 'toggle' ]),
            2)
        self.assertStdout('Usage:')

    @mock.patch('mozpool.bmm.relay.powercycle')
    def run_relay_powercycle(self, rv, exit_code, expected, powercycle):
        powercycle.return_value = rv
        self.assertEqual(self.run_script(
            scripts.relay_script, ['powercycle', 'foo', '1', '2']),
            exit_code)
        powercycle.assert_called_with('foo', 1, 2, timeout=60)
        self.assertStdout(expected)

    def test_relay_powercycle_ok(self):
        self.run_relay_powercycle(True, 0, 'OK')

    def test_relay_powercycle_failed(self):
        self.run_relay_powercycle(False, 1, 'FAILED')

    @mock.patch('mozpool.bmm.relay.get_status')
    def run_relay_status(self, rv, exit_code, expected, get_status):
        get_status.return_value = rv
        self.assertEqual(self.run_script(
            scripts.relay_script, ['status', 'foo', '1', '2']),
            exit_code)
        get_status.assert_called_with('foo', 1, 2, timeout=60)
        self.assertStdout(expected)

    def test_relay_status_on(self):
        self.run_relay_status(True, 0, 'bank 1, relay 2 status: on')

    def test_relay_status_off(self):
        self.run_relay_status(False, 0, 'bank 1, relay 2 status: off')

    def test_relay_status_failed(self):
        self.run_relay_status(None, 1, 'FAILED')

    @mock.patch('mozpool.bmm.relay.set_status')
    def run_turnonoff(self, turnonoff, call_status, rv, exit_code, expected, set_status):
        set_status.return_value = rv
        self.assertEqual(self.run_script(
            scripts.relay_script, [turnonoff, 'foo', '1', '2']),
            exit_code)
        set_status.assert_called_with('foo', 1, 2, call_status, timeout=60)
        self.assertStdout(expected)

    def test_turnoff_ok(self):
        self.run_turnonoff('turnoff', False, True, 0, 'OK')

    def test_turnoff_failed(self):
        self.run_turnonoff('turnoff', False, False, 1, 'FAILED')

    def test_turnon_ok(self):
        self.run_turnonoff('turnon', True, True, 0, 'OK')

    def test_turnon_failed(self):
        self.run_turnonoff('turnon', True, False, 1, 'FAILED')

    # pxe_config scrtipt

    def test_empty(self):
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, []),
            2)
        self.assertStderr('too few')

    def test_list_with_name(self):
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, ['list', 'device1']),
            2)
        self.assertStderr('name is not allowed')

    def test_show_without_name(self):
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, ['show']),
            2)
        self.assertStderr('name is required')

    def test_show_extra_args(self):
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, ['show', 'testy', '--active']),
            2)
        self.assertStderr('any additional')

    def test_add(self):
        self.write_config('this is my config')
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, ['add', 'testy', '-m' 'TEST', '-c', self.test_config_path]),
            None)
        self.assertEqual(self.db.pxe_configs.get('testy'),
                {'description':'TEST', 'contents':'this is my config',
                            'active':True, 'name':'testy'})
        self.assertStdout('this is my')

    def test_modify(self):
        self.write_config('this is my config')
        self.add_pxe_config('testy')
        self.assertEqual(self.run_script(
            scripts.pxe_config_script,
                ['modify', 'testy', '-m' 'TEST', '-c', self.test_config_path, '--inactive']),
            None)
        self.assertEqual(self.db.pxe_configs.get('testy'),
                {'description':'TEST', 'contents':'this is my config',
                            'active':False, 'name':'testy'})
        self.assertStdout('this is my')

    def test_show(self):
        self.add_pxe_config('testy', contents='abcd')
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, ['show', 'testy']),
            None)
        self.assertStdout('abcd')

    def test_list(self):
        self.add_pxe_config('testy1', contents='abcd')
        self.add_pxe_config('testy2', contents='hijk', active=False)
        self.assertEqual(self.run_script(
            scripts.pxe_config_script, ['list']),
            None)
        self.assertStdout('abcd')
        self.assertStdout('hijk')
