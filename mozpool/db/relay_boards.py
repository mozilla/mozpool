# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from sqlalchemy.sql import select
from mozpool.db import model, base

class Methods(base.MethodsBase):

    def get_fqdn(self, name):
        """
        Given relay board name, get its fqdn; raises NotFound if not
        found.
        """
        res = self.db.execute(select([ model.relay_boards.c.fqdn ],
                            whereclause=(model.relay_boards.c.name==name)))
        return self.singleton(res)

    def get_imaging_server(self, name):
        """
        Gets the name of the imaging server associated with this relay board name.
        Raises NotFound if not found.
        """
        res = self.db.execute(select([model.imaging_servers.c.fqdn],
                                from_obj=[model.relay_boards.join(model.imaging_servers)],
                                whereclause=model.relay_boards.c.name == name))
        return self.singleton(res)
