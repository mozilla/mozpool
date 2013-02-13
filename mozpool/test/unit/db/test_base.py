# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from sqlalchemy import select
from mozpool.db import exceptions, base, model
from mozpool.test.util import DBMixin, TestCase

class MyMethods(base.MethodsBase):

    def get_singleton(self, empty=False, missing_ok=False):
        if empty:
            res = self.db.execute("select 1 as a where a = 2")
        else:
            res = self.db.execute("select 1 as a")
        return self.singleton(res, missing_ok=missing_ok)

    def get_column(self):
        res = self.db.execute(select([model.images.c.name]))
        return self.column(res)

    def get_dict_list(self):
        res = self.db.execute(select([model.images.c.name, model.images.c.hidden]))
        return self.dict_list(res)

class Tests(DBMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.db.my = MyMethods(self.db)

    def test_singleton(self):
        self.assertEqual(self.db.my.get_singleton(), 1)
        self.assertEqual(self.db.my.get_singleton(empty=True, missing_ok=True), None)
        self.assertRaises(exceptions.NotFound, lambda :
                self.db.my.get_singleton(empty=True))

    def test_column(self):
        self.add_image('img1')
        self.add_image('img2')
        self.add_image('img3')
        self.assertEqual(sorted(self.db.my.get_column()), ['img1', 'img2', 'img3'])

    def test_dict_list(self):
        self.add_image('img1', hidden=True)
        self.add_image('img2', hidden=False)
        self.add_image('img3', hidden=True)
        self.assertEqual(sorted(self.db.my.get_dict_list()), sorted([
            {'name': 'img1', 'hidden': True},
            {'name': 'img2', 'hidden': False},
            {'name': 'img3', 'hidden': True},
        ]))
