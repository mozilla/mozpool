# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
import datetime
from mozpool.db import exceptions
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    dev1 = {u'environment': None,
            u'relay_info': u'',
            u'name': u'dev1',
            u'fqdn': u'dev1.example.com',
            u'comments': None,
            u'inventory_id': 1,
            u'state': u'occupied',
            u'imaging_server': u'server',
            u'mac_address': u'111111222222',
            u'image': None,
            u'id': 1,
            u'boot_config': u'{}',
            u'request_id' : None}
    dev2 = {u'environment': None,
            u'relay_info': u'',
            u'name': u'dev2',
            u'fqdn': u'dev2.example.com',
            u'comments': None,
            u'inventory_id': 2,
            u'state': u'denial',
            u'imaging_server': u'server',
            u'mac_address': u'000000000000',
            u'image': 'img1',
            u'id': 2,
            u'boot_config': u'{}',
            u'request_id' : None}

    def setUp(self):
        super(Tests, self).setUp()
        self.add_hardware_type('tester', 'premium')
        self.img1_id = self.add_image('img1')
        self.img2_id = self.add_image('img2')
        self.server_id = self.add_server('server')
        self.add_device('dev1', state='occupied', mac_address='111111222222')
        self.add_device('dev2', state='denial', image_id=self.img1_id, next_image_id=self.img2_id)

    def test_list(self):
        self.assertEqual(sorted(self.db.devices.list()), sorted(['dev1', 'dev2']))

    def test_list_detail(self):
        self.assertEqual(sorted(self.db.devices.list(detail=True)),
                sorted([self.dev1, self.dev2]))

    def test_list_detail_request(self):
        dev2 = self.dev2.copy()
        dev2['request_id'] = self.add_request(device='dev2', image='img1')
        self.assertEqual(sorted(self.db.devices.list(detail=True)),
                sorted([self.dev1, dev2]))

    def test_list_available(self):
        # dev1 and dev2 shouldn't show up, because they're not ready

        self.add_device('dev10', environment='staging', state='ready',
                image_id=self.img1_id, boot_config=u'{"a": "b"}')
        dev10 = {'image': 'img1', 'name': u'dev10', 'boot_config': u'{"a": "b"}'}

        self.add_device('dev11', environment='production', state='ready')
        dev11 = {'image': None, 'name': u'dev11', 'boot_config': u'{}'}

        self.add_device('dev12', environment='production', state='ready')
        dev12 = {'image': None, 'name': u'dev12', 'boot_config': u'{}'}

        # distractor that is in state 'ready' but associated with a request, so
        # it should not be seen below
        self.add_device('dev13', state='ready', environment='production')
        self.add_request(device='dev13', image='img1')

        self.assertEqual(sorted(self.db.devices.list_available(environment='staging')),
                sorted([dev10]))
        self.assertEqual(sorted(self.db.devices.list_available(environment='production')),
                sorted([dev11, dev12]))
        self.assertEqual(self.db.devices.list_available(device_name='dev11'), [dev11])
        self.assertEqual(self.db.devices.list_available(device_name='dev10', environment='production'),
                [])
        self.assertEqual(self.db.devices.list_available(device_name='dev1'), [])

    def test_list_states(self):
        self.assertEqual(self.db.devices.list_states(), {u'dev2': u'denial', u'dev1': u'occupied'})

    def test_get_fqdn(self):
        self.assertEqual(self.db.devices.get_fqdn('dev1'), 'dev1.example.com')

    def test_get_fqdn_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_fqdn('dev99'))

    def test_get_imaging_server(self):
        self.assertEqual(self.db.devices.get_imaging_server('dev1'), 'server')

    def test_get_imaging_server_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_imaging_server('dev99'))

    def test_get_mac_address(self):
        self.assertEqual(self.db.devices.get_mac_address('dev1'), '111111222222')

    def test_get_mac_address_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_mac_address('dev99'))

    def test_get_pxe_config_device_next_image(self):
        # set up a pxe_config and link for img1
        self.add_pxe_config('pxe-me')
        self.add_image_pxe_config('img1', 'pxe-me', 'tester', 'premium')
        self.add_device('dev10', next_image_id=self.img1_id)

        self.assertEqual(self.db.devices.get_pxe_config('dev10'), 'pxe-me')

    def test_get_pxe_config_explicit_image(self):
        # set up a pxe_config and link for img1
        self.add_pxe_config('pxe-me')
        self.add_image_pxe_config('img1', 'pxe-me', 'tester', 'premium')
        self.assertEqual(self.db.devices.get_pxe_config('dev2', image='img1'), 'pxe-me')

    def test_get_pxe_config_no_device_image(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_pxe_config('dev1'))

    def test_get_pxe_config_missing_device(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_pxe_config('dev99'))

    def test_get_pxe_config_missing_image(self):
        self.add_device('dev10', image_id=self.img1_id)
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_pxe_config('dev10', image='img99'))

    def test_get_pxe_config_no_suitable_combination(self):
        # there's a device and a pxe config and an image, but the image and
        # pxe config are not connected to one another
        self.add_pxe_config('pxe-me')
        self.add_device('dev10', environment='staging', state='free',
                image_id=self.img1_id)
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_pxe_config('dev10'))

    def test_has_sut_agent_no_image(self):
        self.assertFalse(self.db.devices.has_sut_agent('dev1'))

    def test_has_sut_agent_yes(self):
        img3_id = self.add_image('img3', has_sut_agent=True)
        self.add_device('dev10', image_id=img3_id)
        self.assertTrue(self.db.devices.has_sut_agent('dev10'))

    def test_has_sut_agent_no(self):
        img3_id = self.add_image('img3', has_sut_agent=False)
        self.add_device('dev10', image_id=img3_id)
        self.assertFalse(self.db.devices.has_sut_agent('dev10'))

    def test_has_sut_agent_missing_device(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.has_sut_agent('dev99'))

    def test_get_relay_info(self):
        self.add_device('dev10', relayinfo='relay-fqdn:bank2:relay6')
        self.assertEqual(self.db.devices.get_relay_info('dev10'), ('relay-fqdn', 2, 6))

    def test_get_relay_info_missing_info(self):
        self.add_device('dev10', relayinfo=None)
        self.assertEqual(self.db.devices.get_relay_info('dev10'), None)

    def test_get_relay_info_missing_device(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_relay_info('dev99'))

    def test_get_image(self):
        self.add_device('dev10', image_id=self.img1_id, boot_config='{"a": "b"}')
        self.assertEqual(self.db.devices.get_image('dev10'),
                {'image': 'img1', 'boot_config': '{"a": "b"}'})

    def test_get_image_no_image(self):
        self.assertEqual(self.db.devices.get_image('dev1'),
                {'image': None, 'boot_config': '{}'})

    def test_get_image_no_device(self):
        self.assertEqual(self.db.devices.get_image('dev99'), {})

    def test_set_image(self):
        self.add_image('img3')
        self.db.devices.set_image('dev1', 'img3', 'bc')
        self.assertEqual(self.db.devices.get_image('dev1'),
                {'image': 'img3', 'boot_config': 'bc'})

    def test_set_image_none(self):
        self.db.devices.set_image('dev1', None, None)
        self.assertEqual(self.db.devices.get_image('dev1'),
                {'image': None, 'boot_config': None})

    def test_set_image_no_such(self):
        self.assertRaises(exceptions.NotFound, lambda :
            self.db.devices.set_image('dev1', 'img99', 'bc'))

    def test_get_next_image(self):
        self.add_device('dev10', next_image_id=self.img1_id, next_boot_config='{"a": "b"}')
        self.assertEqual(self.db.devices.get_next_image('dev10'),
                {'image': 'img1', 'boot_config': '{"a": "b"}'})

    def test_get_next_image_no_image(self):
        self.assertEqual(self.db.devices.get_next_image('dev1'),
                {'image': None, 'boot_config': None})

    def test_get_next_image_no_device(self):
        self.assertEqual(self.db.devices.get_next_image('dev99'), {})

    def test_set_next_image(self):
        self.add_image('img3')
        self.db.devices.set_next_image('dev1', 'img3', 'bc')
        self.assertEqual(self.db.devices.get_next_image('dev1'),
                {'image': 'img3', 'boot_config': 'bc'})

    def test_set_next_image_no_such(self):
        self.assertRaises(exceptions.NotFound, lambda :
            self.db.devices.set_next_image('dev1', 'img99', 'bc'))

    def test_set_comments(self):
        self.db.devices.set_comments('dev1', 'howdy')
        commented_dev1 = self.dev1.copy()
        commented_dev1['comments'] = 'howdy'
        self.assertEqual(sorted(self.db.devices.list(detail=True)),
                sorted([commented_dev1, self.dev2]))

    def test_set_environment(self):
        self.db.devices.set_environment('dev1', 'testing')
        testing_dev1 = self.dev1.copy()
        testing_dev1['environment'] = 'testing'
        self.assertEqual(sorted(self.db.devices.list(detail=True)),
                sorted([testing_dev1, self.dev2]))

class TestStateMachineMethods(DBMixin, TestCase):

    def setUp(self):
        super(TestStateMachineMethods, self).setUp()
        self.img1_id = self.add_image('img1')
        self.server_id = self.add_server('server')
        self.add_device('dev1', state='occupied', mac_address='111111222222')
        self.add_device('dev2', state='denial')

    def test_get_machine_state(self):
        self.assertEqual(self.db.devices.get_machine_state('dev1'), 'occupied')

    def test_get_machine_state_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_machine_state('dev99'))

    def test_set_machine_state(self):
        self.db.devices.set_machine_state('dev1', 'unoccupied', datetime.datetime.utcnow())
        self.assertEqual(self.db.devices.get_machine_state('dev1'), 'unoccupied')

    def test_get_counters(self):
        self.add_device('dev3', state_counters='{"a": 1}')
        self.assertEqual(self.db.devices.get_counters('dev3'), {'a': 1})

    def test_get_counters_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.devices.get_counters('dev99'))

    def test_set_counters(self):
        self.db.devices.set_counters('dev1', {'a': 1, 'b': 2})
        self.assertEqual(self.db.devices.get_counters('dev1'), {'a': 1, 'b': 2})

    def test_list_timed_out(self):
        ages_ago = datetime.date(1978, 06, 15)
        tomorrow = datetime.datetime.fromtimestamp(time.time() + 3600*24)
        self.add_server('other')
        self.add_device('dev10', server='other', state_timeout=ages_ago)
        self.add_device('dev11', server='server', state_timeout=ages_ago)
        self.add_device('dev12', server='server', state_timeout=tomorrow)
        self.add_device('dev13', server='server', state_timeout=ages_ago)
        self.assertEqual(sorted(self.db.devices.list_timed_out(self.server_id)),
                         sorted(['dev11', 'dev13']))

class TestObjectLogsMethods(DBMixin, TestCase):

    def setUp(self):
        super(TestObjectLogsMethods, self).setUp()
        self.server_id = self.add_server('server')
        self.dev1_id = self.add_device('dev1')
        self.dev2_id = self.add_device('dev2')

    def test_log_message_and_get_logs(self):
        def now():
            return datetime.datetime(1978, 6, 15)
        self.db.devices.log_message("dev1", "msg1", "tests", _now=now)
        self.db.devices.log_message("dev1", "msg2", "tests", _now=now)
        self.assertEqual(sorted(self.db.devices.get_logs('dev1')), sorted([
            {'timestamp': now().isoformat(), 'message': u'msg1', 'id': 1, 'source': u'tests'},
            {'timestamp': now().isoformat(), 'message': u'msg2', 'id': 2, 'source': u'tests'}
        ]))
        self.assertEqual(self.db.devices.get_logs('dev2'), [])

    def test_get_logs_filtering(self):
        now = datetime.datetime.now()
        def days_ago(d):
            return now - datetime.timedelta(days=d)
        for i in range(100):
            self.db.devices.log_message("dev1", "msg%d" % i, "tests",
                    _now=lambda i=i: days_ago(i))

        def msg_row(i):
            return {'timestamp': days_ago(i).isoformat(), 'message': u'msg%d' % i,
                    'id': i+1, 'source': u'tests'}
        self.assertEqual(sorted(self.db.devices.get_logs('dev1',
                                    timeperiod=datetime.timedelta(hours=12))),
                         sorted([msg_row(i) for i in (0,)]))
        self.assertEqual(sorted(self.db.devices.get_logs('dev1',
                                    timeperiod=datetime.timedelta(hours=36))),
                         sorted([msg_row(i) for i in (0, 1)]))
        self.assertEqual(sorted(self.db.devices.get_logs('dev1',
                                    timeperiod=datetime.timedelta(days=5))),
                         sorted([msg_row(i) for i in (0, 1, 2, 3, 4)]))
        self.assertEqual(sorted(self.db.devices.get_logs('dev1',
                                    timeperiod=datetime.timedelta(days=5),
                                    limit=3)),
                         sorted([msg_row(i) for i in (0, 1, 2)]))
        self.assertEqual(sorted(self.db.devices.get_logs('dev1',
                                    limit=3)),
                         sorted([msg_row(i) for i in (0, 1, 2)]))

    def test_delete_all_logs(self):
        def now():
            return datetime.datetime(1978, 6, 15)
        self.db.devices.log_message("dev1", "msg1", "tests", _now=now)
        self.db.devices.log_message("dev1", "msg2", "tests", _now=now)
        self.db.devices.log_message("dev2", "msg3", "tests", _now=now)
        self.db.devices.delete_all_logs(self.dev1_id)
        self.assertEqual(self.db.devices.get_logs('dev1'), [])
        self.assertEqual(sorted(self.db.devices.get_logs('dev2')), sorted([
            {'timestamp': now().isoformat(), 'message': u'msg3', 'id': 3, 'source': u'tests'}
        ]))
