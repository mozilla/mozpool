# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from sqlalchemy.sql import select
from mozpool.db import model, base, exceptions

class Methods(base.MethodsBase):

    def list(self, active_only=False):
        """
        Return a list of the names of all PXE configs.  If active_only is true,
        then only active PXE configs are returned.
        """
        q = select([model.pxe_configs.c.name])
        if active_only:
            q = q.where(model.pxe_configs.c.active)
        res = self.db.execute(q)
        return self.column(res)

    def get(self, pxe_config_name):
        """
        Get the details about a particular pxe_config.  The details are
        represented as a dictionary with keys 'name', 'description',
        'contents', and 'active'.  Raises NotFound if no such PXE config
        exists.
        """
        res = self.db.execute(select([model.pxe_configs],
                                model.pxe_configs.c.name==pxe_config_name))
        rows = self.dict_list(res)
        if not rows:
            raise exceptions.NotFound
        # remove 'id'
        result = rows[0]
        del result['id']
        return result

    def add(self, name, description, active, contents):
        """
        Add a new PXE config with the given parameters.
        """
        self.db.execute(model.pxe_configs.insert(),
                [ {'name':name, 'description':description, 'active':active, 'contents':contents} ])

    def update(self, name, description=None, active=None, contents=None):
        """
        Update the given PXE config with the given parameters.  Unspecified
        parameters are not changed.
        """
        updates = {}
        if description:
            updates['description'] = description
        if active is not None:
            updates['active'] = active
        if contents is not None:
            updates['contents'] = contents
        self.db.execute(model.pxe_configs.update(
                        model.pxe_configs.c.name == name),
                    **updates)

