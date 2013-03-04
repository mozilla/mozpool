# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import datetime
import mozpool.mozpool
from mozpool import config
from mozpool.test.util import TestCase, AppMixin, DBMixin, ConfigMixin

class Tests(AppMixin, DBMixin, ConfigMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        config.set('server', 'fqdn', 'server')
        self.add_server('server')
        self.add_image('img1', boot_config_keys='[]')
        self.add_image('img2', boot_config_keys='["aa", "bb"]')
        self.dev_id = self.add_device('dev1', environment='abc')

        mozpool.mozpool.driver = mock.Mock()

    def test_device_list(self):
        body = self.check_json_result(self.app.get('/api/device/list/'))
        self.assertEqual(body, {'devices': ['dev1']})

    def test_device_list_details(self):
        req_id = self.add_request(device='dev1', image='img2')
        body = self.check_json_result(self.app.get('/api/device/list/?details=1'))
        self.assertEqual(body, {u'devices': [
            {u'boot_config': u'{}',
             u'comments': None,
             u'environment': u'abc',
             u'fqdn': u'dev1.example.com',
             u'id': 1,
             u'image': None,
             u'imaging_server': u'server',
             u'inventory_id': 1,
             u'mac_address': u'000000000000',
             u'name': u'dev1',
             u'relay_info': u'',
             u'request_id': req_id,
             u'state': u'offline'}]})

    def test_device_request_fails(self):
        r = self.post_json('/api/device/dev1/request/', {}, expect_errors=True)
        self.assertEqual(r.status, 400)

    def test_device_request_unknown_image(self):
        r = self.post_json('/api/device/dev1/request/',
            {'assignee': 'me', 'duration': 10, 'image': 'unk', 'environment': 'prod'},
            expect_errors=True)
        self.assertEqual(r.status, 404)

    def test_device_request_missing_keys(self):
        r = self.post_json('/api/device/dev1/request/',
            {'assignee': 'me', 'duration': 10, 'image': 'img2', 'environment': 'prod',
             'aa': 'x'},
            expect_errors=True)
        self.assertEqual(r.status, 400)

    def test_device_request_good(self):
        body = self.check_json_result(self.post_json('/api/device/dev1/request/',
            {'assignee': 'me', 'duration': 10, 'image': 'img2', 'environment': 'prod',
             'aa': 'x', 'bb': 'y'}))
        mozpool.mozpool.driver.handle_event.assert_called_with(1, 'find_device', None)
        body['request'].pop('expires') # value is time-dependent
        self.assertEqual(body, {'request':
                       {'assigned_device': '',
                        'assignee': 'me',
                        'boot_config': '{"aa": "x", "bb": "y"}',
                        'environment': 'prod',
                        #'expires': '2013-02-22T22:29:06.412207',
                        'id': 1,
                        'image': 'img2',
                        'requested_device': 'dev1',
                        'url': 'http://server/api/request/1/'}})

    def test_device_request_conflict(self):
        "if the state machine closes the request right away, the API returns 409"
        def close_req(*args, **kwargs):
            self.db.requests.set_machine_state(1, 'closed', None)
        mozpool.mozpool.driver.handle_event.side_effect = close_req
        r = self.post_json('/api/device/dev1/request/',
            {'assignee': 'me', 'duration': 10, 'image': 'img2', 'environment': 'prod',
             'aa': 'x', 'bb': 'y'},
            expect_errors=True)
        self.assertEqual(r.status, 409)

    def test_request_list(self):
        self.add_request(device='dev1', image='img1', server='server', no_assign=True)
        body = self.check_json_result(self.app.get('/api/request/list/'))
        [ rq.pop('expires') for rq in body['requests'] ] # value is time-dependent
        self.assertEqual(body, {'requests': [
            {'requested_device': 'dev1',
             'boot_config': '{}',
             #'expires': '2013-02-22T18:46:09.969519',
             'device_state': '',
             'assigned_device': '',
             'environment': None,
             'assignee': 'slave',
             'state': 'new',
             'imaging_server': 'server',
             'id': 1},
        ]})

    def test_request_details(self):
        req_id = self.add_request(device='dev1', image='img1', server='server', no_assign=True)
        body = self.check_json_result(self.app.get('/api/request/%s/details/' % req_id))
        body.pop('expires') # value is time-dependent
        self.assertEqual(body, {
            'requested_device': 'dev1',
            'url': 'http://server/api/request/%d/' % req_id,
            'image': 'img1',
            #'expires': '2013-02-22T18:51:29.446573',
            'assigned_device': '',
            'environment': None,
            'assignee': 'slave',
            'boot_config': '{}',
            'id': req_id,
        })

    def test_request_details_bad_id(self):
        r = self.app.get('/api/request/xyz/details/', expect_errors=True)
        self.assertEqual(r.status, 400)

    def test_request_details_missing(self):
        r = self.app.get('/api/request/99/details/', expect_errors=True)
        self.assertEqual(r.status, 404)

    def test_request_status(self):
        req_id = self.add_request(image='img1', server='server', state='thinking', no_assign=True)
        self.add_request_log(1, 'hello', 'test', datetime.datetime(1978, 6, 15))
        self.add_request_log(1, 'goodbye', 'test', datetime.datetime(1978, 6, 16))
        body = self.check_json_result(self.app.get('/api/request/%s/status/' % req_id))
        self.assertEqual(body, {'state': 'thinking', 'log': [
            {u'id': 1, u'message': u'hello', u'source': u'test', u'timestamp': u'1978-06-15T00:00:00'},
            {u'id': 2, u'message': u'goodbye', u'source': u'test', u'timestamp': u'1978-06-16T00:00:00'},
        ]})

    def test_request_log(self):
        req_id = self.add_request(image='img1', server='server', state='thinking', no_assign=True)
        self.add_request_log(1, 'hello', 'test', datetime.datetime(1978, 6, 15))
        self.add_request_log(1, 'goodbye', 'test', datetime.datetime(1978, 6, 16))
        body = self.check_json_result(self.app.get('/api/request/%s/log/' % req_id))
        self.assertEqual(body, {'log': [
            {u'id': 1, u'message': u'hello', u'source': u'test', u'timestamp': u'1978-06-15T00:00:00'},
            {u'id': 2, u'message': u'goodbye', u'source': u'test', u'timestamp': u'1978-06-16T00:00:00'},
        ]})

    @mock.patch("mozpool.db.requests.Methods.renew")
    def test_request_renew(self, renew):
        req_id = self.add_request(image='img1', server='server', no_assign=True)
        r = self.post_json('/api/request/%s/renew/' % req_id, {'duration': 3600})
        renew.assert_called_with(req_id, 3600)
        self.assertEqual(r.status, 204)

    def test_request_renew_bad_duration(self):
        req_id = self.add_request(image='img1', server='server', no_assign=True)
        r = self.post_json('/api/request/%s/renew/' % req_id, {'duration': 'abcd'}, expect_errors=True)
        self.assertEqual(r.status, 400)

    def test_request_return(self):
        req_id = self.add_request(image='img1', server='server', no_assign=True)
        r = self.post_json('/api/request/%s/return/' % req_id, {})
        mozpool.mozpool.driver.handle_event.assert_called_with(req_id, 'close', None)
        self.assertEqual(r.status, 204)

    def test_event_GET(self):
        req_id = self.add_request(image='img1', server='server', no_assign=True)
        self.check_json_result(self.app.get('/api/request/%s/event/shorted/' % req_id))
        mozpool.mozpool.driver.handle_event.assert_called_with(req_id, 'shorted', {})

    def test_event_POST(self):
        req_id = self.add_request(image='img1', server='server', no_assign=True)
        self.check_json_result(self.post_json('/api/request/%s/event/shorted/' % req_id, {'a': 'b'}))
        mozpool.mozpool.driver.handle_event.assert_called_with(req_id, 'shorted', {'a': 'b'})

    def test_image_list(self):
        body = self.check_json_result(self.app.get('/api/image/list/'))
        body['images'].sort()
        self.assertEqual(body, {u'images': sorted([
               {'boot_config_keys': [],
                'can_reuse': False,
                'has_sut_agent': True,
                'hidden': False,
                'id': 1,
                'name': u'img1'},
               {'boot_config_keys': [u'aa', u'bb'],
                'can_reuse': False,
                'has_sut_agent': True,
                'hidden': False,
                'id': 2,
                'name': u'img2'},
        ])})
