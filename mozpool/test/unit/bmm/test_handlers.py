# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import datetime
from mozpool import config
from mozpool.test.util import TestCase, AppMixin, DBMixin, ConfigMixin, PatchMixin

class Tests(AppMixin, DBMixin, ConfigMixin, PatchMixin, TestCase):

    auto_patch = [
        ('set_pxe', 'mozpool.bmm.api.API.set_pxe'),
        ('clear_pxe', 'mozpool.bmm.api.API.clear_pxe'),
        ('powercycle', 'mozpool.bmm.api.API.powercycle'),
        ('poweroff', 'mozpool.bmm.api.API.poweroff'),
        ('ping', 'mozpool.bmm.api.API.ping'),
        ('get_logs', 'mozpool.db.base.ObjectLogsMethodsMixin.get_logs'),
        ('test_two_way_comms', 'mozpool.bmm.api.API.test_two_way_comms'),
    ]

    def setUp(self):
        super(Tests, self).setUp()
        config.set('server', 'fqdn', 'server')
        self.add_server('server')
        img_id = self.add_image('img1')
        self.dev_id = self.add_device('dev1', environment='abc', next_image_id=img_id)
        self.add_relay_board('relay1', server='server')

    def test_device_power_cycle(self):
        self.check_json_result(self.post_json('/api/device/dev1/power-cycle/', {}))
        self.set_pxe.run.assert_not_called()
        self.clear_pxe.run.assert_called_with('dev1')
        self.powercycle.start.assert_called_with(mock.ANY, 'dev1')

    def test_device_power_cycle_pxe(self):
        self.check_json_result(self.post_json('/api/device/dev1/power-cycle/',
            {'pxe_config': '123'}))
        self.set_pxe.run.assert_called_with('dev1', '123')
        self.clear_pxe.assert_not_called()
        self.powercycle.start.assert_called_with(mock.ANY, 'dev1')

    def test_device_power_cycle_pxe_boot_config(self):
        self.check_json_result(self.post_json('/api/device/dev1/power-cycle/',
            {'pxe_config': '123', 'boot_config': 'abc'}))
        self.set_pxe.run.assert_called_with('dev1', '123')
        self.clear_pxe.assert_not_called()
        self.powercycle.start.assert_called_with(mock.ANY, 'dev1')
        self.assertEqual(self.db.devices.get_next_image('dev1')['boot_config'], 'abc')

    def test_device_power_off(self):
        self.check_json_result(self.app.get('/api/device/dev1/power-off/'))
        self.poweroff.start.assert_called_with(mock.ANY, 'dev1')

    def test_device_ping(self):
        self.ping.run.return_value = True
        body = self.check_json_result(self.app.get('/api/device/dev1/ping/'))
        # note that this runs the ping synchronously
        self.ping.run.assert_called_with('dev1')
        self.assertEqual(body, {'success': True})

    def test_device_ping_fails(self):
        self.ping.run.return_value = False
        body = self.check_json_result(self.app.get('/api/device/dev1/ping/'))
        self.assertEqual(body, {'success': False})

    def test_device_clear_pxe(self):
        self.check_json_result(self.post_json('/api/device/dev1/clear-pxe/', {}))
        self.clear_pxe.run.assert_called_with('dev1')

    def test_device_log(self):
        # NOTE: datetime can't be patched, so we patch get_logs instead
        self.get_logs.return_value = [{'a': 'b'}]
        body = self.check_json_result(self.app.get('/api/device/dev1/log/'))
        self.assertEqual(body, {'log': [{'a': 'b'}]})
        self.get_logs.assert_called_with('dev1', timeperiod=None, limit=None)

        self.get_logs.reset_mock()
        body = self.check_json_result(self.app.get('/api/device/dev1/log/?timeperiod=1'))
        self.get_logs.assert_called_with('dev1', timeperiod=datetime.timedelta(seconds=1), limit=None)

        self.get_logs.reset_mock()
        body = self.check_json_result(self.app.get('/api/device/dev1/log/?timeperiod=1&limit=2'))
        self.get_logs.assert_called_with('dev1', timeperiod=datetime.timedelta(seconds=1), limit=2)

        self.get_logs.reset_mock()
        body = self.check_json_result(self.app.get('/api/device/dev1/log/?limit=2'))
        self.get_logs.assert_called_with('dev1', timeperiod=None, limit=2)

    @mock.patch('mozpool.db.devices.Methods.set_comments')
    def test_device_set_comments(self, set_comments):
        self.check_json_result(self.post_json('/api/device/dev1/set-comments/',
                                                     {'comments': 'hi'}))
        set_comments.assert_called_with('dev1', 'hi')

    @mock.patch('mozpool.db.devices.Methods.set_environment')
    def test_device_set_environment(self, set_environment):
        self.check_json_result(self.post_json('/api/device/dev1/set-environment/',
                                                     {'environment': 'hi'}))
        set_environment.assert_called_with('dev1', 'hi')

    def test_device_bootconfig(self):
        self.add_device('dev2', next_boot_config='{"a": "b"}')
        body = self.check_json_result(self.app.get('/api/device/dev2/bootconfig/'))
        self.assertEqual(body, {'a': 'b'})

    def test_environment_list(self):
        body = self.check_json_result(self.app.get('/api/environment/list/'))
        self.assertEqual(body, {'environments': ['abc']})

    def test_pxe_config_list(self):
        self.add_pxe_config('pxe1', active=True)
        self.add_pxe_config('pxe2', active=False)
        body = self.check_json_result(self.app.get('/api/bmm/pxe_config/list/'))
        self.assertEqual(body, {'pxe_configs': ['pxe1', 'pxe2']})
        body = self.check_json_result(self.app.get('/api/bmm/pxe_config/list/?active_only=1'))
        self.assertEqual(body, {'pxe_configs': ['pxe1']})

    def test_pxe_config_details(self):
        self.add_pxe_config('pxe1', description='D', contents='C', id=8, active=True)
        body = self.check_json_result(self.app.get('/api/bmm/pxe_config/pxe1/details/'))
        self.assertEqual(body, {'details': {'active': True,
                                            'contents': u'C',
                                            'description': u'D',
                                            'name': u'pxe1'}})

    def test_test_two_way_comms(self):
        self.test_two_way_comms.run.return_value = True
        body = self.check_json_result(self.app.get('/api/relay/relay1/test/'))
        self.test_two_way_comms.run.assert_called_with('relay1')
        self.assertEqual(body, {'success': True})

    def test_test_two_way_comms_fails(self):
        self.test_two_way_comms.run.return_value = False
        body = self.check_json_result(self.app.get('/api/relay/relay1/test/'))
        self.assertEqual(body, {'success': False})