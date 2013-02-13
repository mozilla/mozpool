# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy
from mozpool.db import model, base

class Methods(base.MethodsBase):

    def list(self):
        """
        Return a list of all environments that contain at least one device, by
        name.
        """
        res = self.db.execute(
                sqlalchemy.select([sqlalchemy.distinct(model.devices.c.environment)]))
        return self.column(res)

