# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy
from sqlalchemy.sql import select
from mozpool.db import model, base

class Methods(base.MethodsBase):

    def add(self, request_id, device_name):
        """
        Add a new device request, for the given request (by ID) and device (by
        name).  Raises NotFound if no such device exists.  Returns True on
        success, or False on failure (usually because the device is already
        tied to a request)
        """
        res = self.db.execute(select(
                [model.devices.c.id],
                model.devices.c.name==device_name))
        device_id = self.singleton(res)

        try:
            self.db.execute(model.device_requests.insert(),
                        {'request_id': request_id,
                         'device_id': device_id,
                         'imaging_result': None})
        except sqlalchemy.exc.IntegrityError:
            return False
        return True

    def clear(self, request_id):
        """
        Clear the association between the given request and its device.  This
        will silently succeed if the request has no associated device.
        """
        self.db.execute(model.device_requests.delete().where(
                model.device_requests.c.request_id==request_id))

    def get_by_device(self, device_name):
        """
        Return the request id connected to the given device name, or None if
        there is no connection.
        """
        res = self.db.execute(select(
                [model.device_requests.c.request_id],
                from_obj=[model.device_requests.join(model.devices)]).where(
                model.devices.c.name==device_name))
        return self.singleton(res, missing_ok=True)

    def set_result(self, device_name, result):
        """
        Set the imaging result string for the device request attached to the
        given device.  Raises NotFound if no such device exists, but does
        nothing if the device is not assigned.
        """
        res = self.db.execute(select(
            [model.devices.c.id],
            whereclause=(model.devices.c.name==device_name)))
        device_id = self.singleton(res)

        q = model.device_requests.update(
                whereclause=model.device_requests.c.device_id==device_id)
        self.db.execute(q, imaging_result=result)

    def get_result(self, request_id):
        """
        Return the imaging results for the device request attached to the given
        request, or None if there is no attached device request.
        """
        res = self.db.execute(select(
                [model.device_requests.c.imaging_result],
                whereclause=(model.device_requests.c.request_id==request_id)))
        return self.singleton(res, missing_ok=True)
