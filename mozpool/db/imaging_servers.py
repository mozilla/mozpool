# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy
from sqlalchemy.sql import select
from mozpool.db import model, base

class Methods(base.MethodsBase):

    def get_id(self, fqdn):
        """
        Given an imaging server fqdn, get its ID; raises NotFound if not
        found.
        """
        res = self.db.execute(sqlalchemy.select([ model.imaging_servers.c.id ],
                            whereclause=(model.imaging_servers.c.fqdn==fqdn)))
        return self.singleton(res)

    def list(self):
        """
        Return a list of the fqdn's of all imaging servers
        """
        res = self.db.execute(select([model.imaging_servers.c.fqdn]))
        return self.column(res)

