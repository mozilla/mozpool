# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import threading
import mock
from mozpool.bmm import api, pxe
from mozpool.test.util import ConfigMixin, DBMixin, TestCase

class TestBmmApi(DBMixin, ConfigMixin, TestCase):

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
        a = api.API(self.db)
        return self.wait_for_async(lambda cb :
            a.start_powercycle(device_name, cb, max_time))

    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.relay.powercycle')
    @mock.patch('mozpool.db.devices.Methods.get_relay_info')
    def test_good(self, device_relay_info, powercycle, log_message):
        device_relay_info.return_value = ('relay1', 1, 3)
        powercycle.return_value = True
        self.assertEqual(self.do_call_start_powercycle('dev1', max_time=30), True)
        device_relay_info.assert_called_with('dev1')
        powercycle.assert_called_with('relay1', 1, 3, 30)
        log_message.assert_called()

    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.relay.powercycle')
    @mock.patch('mozpool.db.devices.Methods.get_relay_info')
    def test_bad(self, device_relay_info, powercycle, log_message):
        device_relay_info.return_value = ('relay1', 1, 3)
        powercycle.return_value = False
        self.assertEqual(self.do_call_start_powercycle('dev1', max_time=30), False)
        log_message.assert_called()

    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.relay.powercycle')
    @mock.patch('mozpool.db.devices.Methods.get_relay_info')
    def test_exceptions(self, device_relay_info, powercycle, log_message):
        device_relay_info.return_value = ('relay1', 1, 3)
        powercycle.return_value = False
        powercycle.side_effect = lambda *args : 11/0 # ZeroDivisionError
        self.assertEqual(self.do_call_start_powercycle('dev1', max_time=0.01), False)
        log_message.assert_called()

    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.pxe.set_pxe')
    def test_set_pxe(self, pxe_set_pxe, log_message):
        pxe.set_pxe('device1', 'img1', 'cfg')
        pxe_set_pxe.assert_called_with('device1', 'img1', 'cfg')
        log_message.assert_called()

    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.pxe.clear_pxe')
    def test_clear_pxe(self, pxe_clear_pxe, log_message):
        pxe.clear_pxe('device1')
        pxe_clear_pxe.assert_called_with('device1')
        log_message.assert_called()

    def do_call_start_ping(self, device_name):
        a = api.API(self.db)
        return self.wait_for_async(lambda cb :
            a.start_ping(device_name, cb))

    @mock.patch('mozpool.db.devices.Methods.get_fqdn')
    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.ping.ping')
    def test_start_ping(self, ping, log_add, device_fqdn):
        ping.return_value = True
        device_fqdn.return_value = 'abcd'
        self.do_call_start_ping('xyz')
        device_fqdn.assert_called_with('xyz')
        log_add.assert_called()
        ping.assert_called_with('abcd')

    @mock.patch('mozpool.db.devices.Methods.get_fqdn')
    @mock.patch('mozpool.db.base.ObjectLogsMethodsMixin.log_message')
    @mock.patch('mozpool.bmm.ping.ping')
    def test_ping(self, ping, log_message, device_fqdn):
        ping.return_value = True
        device_fqdn.return_value = 'abcd'
        a = api.API(self.db)
        a.ping('xyz')
        device_fqdn.assert_called_with('xyz')
        log_message.assert_called()
        ping.assert_called_with('abcd')
