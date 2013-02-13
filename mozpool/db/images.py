# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import sqlalchemy
from sqlalchemy.sql import select
from mozpool.db import model, base, exceptions

class Methods(base.MethodsBase):

    def _row_to_dict(self, row):
        img = dict(row)
        if img['boot_config_keys']:
            img['boot_config_keys'] = json.loads(img['boot_config_keys'])
        else:
            img['boot_config_keys'] = []
        return img

    def list(self):
        """
        Get information about all visible images, represented as dictionaries
        with keys 'id', 'name', 'boot_config_keys', 'can_reuse', 'hidden', and
        'has_sut_agent'.
        """
        stmt = sqlalchemy.select([model.images])
        stmt = stmt.where(sqlalchemy.not_(model.images.c.hidden))
        res = self.db.execute(stmt)
        return [self._row_to_dict(r) for r in res.fetchall()]

    def get(self, image_name):
        """
        Get information about the named image.  The result is a dictionary
        with keys 'id', 'name', 'boot_config_keys', 'can_reuse', 'hidden',
        and 'has_sut_agent'.  Raises NotFound if no such image exists.
        """
        stmt = sqlalchemy.select([model.images])
        stmt = stmt.where(model.images.c.name==image_name)
        res = self.db.execute(stmt)
        row = res.fetchone()
        if not row:
            raise exceptions.NotFound
        return self._row_to_dict(row)

    def is_reusable(self, image_name):
        """
        Is the named image reusable?  Raises NotFound if no such image exists.
        """
        res = self.db.execute(select([model.images.c.can_reuse],
                                            model.images.c.name==image_name))
        return self.singleton(res)
