# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import mock
import time
import json
import datetime
import web
import templeton.handlers
from paste.fixture import TestApp
from mozpool.web import handlers
from mozpool import config
from mozpool.test.util import TestCase, DBMixin, ConfigMixin

class DevTestHandler(handlers.Handler):

    @handlers.deviceredirect
    def GET(self, device_name):
        web.header('Content-Type', 'text/plain')
        return "hi"


class ReqTestHandler(handlers.Handler):

    @handlers.requestredirect
    def GET(self, request_id):
        web.header('Content-Type', 'text/plain')
        return "hi"

class RelayTestHandler(handlers.Handler):

    @handlers.relayredirect
    def GET(self, request_id):
        web.header('Content-Type', 'text/plain')
        return "hi"


class CachedHandler(handlers.InMemCacheMixin, handlers.Handler):

    updates = []
    CACHE_TTL = 10

    def update_cache(self):
        self.updates.append(time.time())

    @templeton.handlers.json_response
    def GET(self):
        self.cache_get()
        return {}


class Tests(TestCase):

    def test_DateTimeJSONEncoder(self):
        dt = datetime.datetime(1978, 6, 15)
        self.assertEqual(json.dumps([dt, 1], cls=handlers.DateTimeJSONEncoder),
                '["1978-06-15T00:00:00", 1]')

    @mock.patch('time.time')
    def test_InMemCacheMixin(self, time):
        loaded_urls = templeton.handlers.load_urls([
            '/test/', 'CachedHandler',
        ])
        webapp = web.application(loaded_urls, globals())
        self.app = TestApp(webapp.wsgifunc())

        CachedHandler.updates = []
        time.return_value = 10

        for i in xrange(30):
            self.app.get('/api/test/')
            time.return_value += 1

        self.assertEqual(CachedHandler.updates, [10, 20, 30])


class RedirectTests(DBMixin, ConfigMixin, TestCase):

    def setUp(self):
        super(RedirectTests, self).setUp()

        config.set('server', 'fqdn', 'thisserver')
        self.add_server('thisserver')
        self.add_server('otherserver')
        self.add_device('dev1', server='thisserver')
        self.add_device('dev2', server='otherserver')
        self.add_image('b2g')
        self.add_request(server='thisserver', no_assign=True) # id=1
        self.add_request(server='otherserver', no_assign=True) # id=2
        self.add_relay_board(relay_board='relay1', server='thisserver')
        self.add_relay_board(relay_board='relay2', server='otherserver')

        handlers.Handler.db = self.db
        loaded_urls = templeton.handlers.load_urls([
            '/device/([^/]+)/test/?', 'DevTestHandler',
            '/request/([^/]+)/test/?', 'ReqTestHandler',
            '/relay/([^/]+)/test/?', 'RelayTestHandler',
        ])
        webapp = web.application(loaded_urls, globals())
        self.app = TestApp(webapp.wsgifunc())

    def test_deviceredirect_thisserver(self):
        r = self.app.get('/api/device/dev1/test/',
                headers={'Origin': 'http://otherserver'})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.header('Access-Control-Allow-Origin'), 'http://otherserver')

    def test_deviceredirect_302(self):
        r = self.app.get('/api/device/dev2/test/')
        self.assertEqual(r.status, 302)
        self.assertEqual(r.header('Location'), 'http://otherserver/api/device/dev2/test/')

    def test_deviceredirect_403(self):
        "requests from an origin that's not an imaging server are forbidden"
        r = self.app.get('/api/device/dev1/test/',
                headers={'Origin': 'http://notanimgingserver'},
                expect_errors=True)
        self.assertEqual(r.status, 403)

    def test_deviceredirect_404(self):
        r = self.app.get('/api/device/dev99/test/', expect_errors=True)
        self.assertEqual(r.status, 404)

    def test_requestredirect_thisserver(self):
        r = self.app.get('/api/request/1/test/')
        self.assertEqual(r.status, 200)

    def test_requestredirect_302(self):
        r = self.app.get('/api/request/2/test/')
        self.assertEqual(r.status, 302)
        self.assertEqual(r.header('Location'), 'http://otherserver/api/request/2/test/')

    def test_requestredirect_404(self):
        r = self.app.get('/api/request/99/test/', expect_errors=True)
        self.assertEqual(r.status, 404)

    def test_relayredirect_thisserver(self):
        r = self.app.get('/api/relay/relay1/test/')
        self.assertEqual(r.status, 200)

    def test_relayredirect_302(self):
        r = self.app.get('/api/relay/relay2/test/')
        self.assertEqual(r.status, 302)
        self.assertEqual(r.header('Location'), 'http://otherserver/api/relay/relay2/test/')

    def test_relayredirect_404(self):
        r = self.app.get('/api/relay/relay99/test/', expect_errors=True)
        self.assertEqual(r.status, 404)
