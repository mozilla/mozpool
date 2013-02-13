# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.db import exceptions
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.add_pxe_config('blackberry', description="Install BBOS",
                contents="secret",
                id=2, active=True)
        self.add_pxe_config('ios', description="Install iOS",
                contents="if I told you I'd have to kill you",
                id=3, active=False)

    def test_list(self):
        self.assertEqual(sorted(self.db.pxe_configs.list()), ['blackberry', 'ios'])
        self.assertEqual(self.db.pxe_configs.list(active_only=True), ['blackberry'])

    def test_get(self):
        self.assertEqual(self.db.pxe_configs.get('blackberry'), {
            'active': True, 'contents': 'secret', 'description': 'Install BBOS',
            'name': 'blackberry'})

    def test_get_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
            self.db.pxe_configs.get('winmobile'))

    def test_add(self):
        self.db.pxe_configs.add('maintenance', 'maint mode', True, 'maintain!')
        self.assertEqual(self.db.pxe_configs.get('maintenance'), {
            'active': True, 'contents': 'maintain!', 'description': 'maint mode',
            'name': 'maintenance'})

    def test_update(self):
        self.db.pxe_configs.update('ios', 'not really', True, 'exit 1')
        self.assertEqual(self.db.pxe_configs.get('ios'), {
            'active': True, 'contents': 'exit 1', 'description': 'not really',
            'name': 'ios'})
