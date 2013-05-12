# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
from mozpool.bmm import api
from mozpool.test.util import ConfigMixin, DBMixin, TestCase

class Tests(DBMixin, ConfigMixin, TestCase):

    # note that this does not test the async stuff, and just uses run

    def setUp(self):
        super(Tests,self).setUp()
        self.add_server('server')
        self.add_device('dev1', relayinfo='rly:bank1:relay2',
                mac_address='aabbccddeeff')
        self.add_relay_board('relay1', server='server')
        self.api = api.API(self.db)

    @mock.patch('mozpool.bmm.relay.powercycle')
    def test_powercycle(self, powercycle):
        self.api.powercycle.run('dev1')
        powercycle.assert_called_with('rly', 1, 2, 30)

    @mock.patch('mozpool.bmm.relay.set_status')
    def test_poweroff(self, set_status):
        self.api.poweroff.run('dev1')
        set_status.assert_called_with('rly', 1, 2, False, 30)

    @mock.patch('mozpool.bmm.pxe.set_pxe')
    def test_set_pxe(self, set_pxe):
        self.add_pxe_config('abc', contents='PXE CFG')
        self.api.set_pxe.run('dev1', 'abc')
        set_pxe.assert_called_with('aabbccddeeff', 'PXE CFG')

    @mock.patch('mozpool.bmm.pxe.clear_pxe')
    def test_clear_pxe(self, clear_pxe):
        self.api.clear_pxe.run('dev1')
        clear_pxe.assert_called_with('aabbccddeeff')

    @mock.patch('mozpool.bmm.ping.ping')
    def test_ping(self, ping):
        self.api.ping.run('dev1')
        ping.assert_called_with('dev1.example.com')

    @mock.patch('mozpool.bmm.sut.sut_verify')
    def test_sut_verify(self, sut_verify):
        self.api.sut_verify.run('dev1')
        sut_verify.assert_called_with('dev1.example.com')

    @mock.patch('mozpool.bmm.sut.check_sdcard')
    def test_check_sdcard(self, check_sdcard):
        self.api.check_sdcard.run('dev1')
        check_sdcard.assert_called_with('dev1.example.com')

    @mock.patch('mozpool.bmm.relay.test_two_way_comms')
    def test_two_way_comms(self, test_two_way_comms):
        self.api.test_two_way_comms.run('relay1')
        test_two_way_comms.assert_called_with('relay1.example.com', 10)
