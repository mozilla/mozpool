# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.db import exceptions
from mozpool.test.util import DBMixin, TestCase

class Tests(DBMixin, TestCase):

    img1 = {u'boot_config_keys': [u'a'],
            u'name': u'i1',
            u'id': 10,
            u'has_sut_agent': True,
            u'can_reuse': False,
            u'hidden': False}
    img2 = {u'boot_config_keys': [u'b'],
            u'name': u'i2',
            u'id': 11,
            u'has_sut_agent': False,
            u'can_reuse': True,
            u'hidden': True}

    def setUp(self):
        super(Tests, self).setUp()
        self.add_image('i1', boot_config_keys='["a"]', can_reuse=False, id=10,
                    hidden=False, has_sut_agent=True)
        self.add_image('i2', boot_config_keys='["b"]', can_reuse=True, id=11,
                    hidden=True, has_sut_agent=False)

    def test_list(self):
        # note this only shows *visible* images
        self.assertEqual(sorted(self.db.images.list()), sorted([self.img1]))

    def test_get(self):
        self.assertEqual(self.db.images.get('i1'), self.img1)
        self.assertEqual(self.db.images.get('i2'), self.img2)

    def test_get_null_boot_config_keys(self):
        self.add_image('i3', boot_config_keys=None)
        self.assertEqual(self.db.images.get('i3')['boot_config_keys'], [])

    def test_get_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.images.get('i99'))

    def test_is_reusable(self):
        self.assertFalse(self.db.images.is_reusable('i1'))
        self.assertTrue(self.db.images.is_reusable('i2'))

    def test_is_reusable_missing(self):
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.images.is_reusable('i99'))
