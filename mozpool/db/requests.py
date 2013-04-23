# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import sqlalchemy
from sqlalchemy.sql import select, not_
from mozpool.db import model, base, exceptions
from mozpool import config

class Methods(base.MethodsBase,
        base.ObjectLogsMethodsMixin,
        base.StateMachineMethodsMixin):

    state_machine_table = model.requests
    state_machine_id_column = model.requests.c.id

    logs_table = model.request_logs
    foreign_key_col = model.request_logs.c.request_id

    def _get_object_id(self, object_name):
        # requests are referred to by id, so name == id
        return object_name

    def add(self, requested_device, environment, assignee, duration, image_id,
            boot_config, _now=datetime.datetime.utcnow):
        """
        Add a new request with the given parameters.  The state is set to
        'new'.

        Returns the ID of the new request.
        """
        server_id = self.db.execute(select(
                [model.imaging_servers.c.id],
                model.imaging_servers.c.fqdn==config.get('server', 'fqdn'))
                                ).fetchall()[0][0]
        request = {'imaging_server_id': server_id,
                    'requested_device': requested_device,
                    'environment': environment,
                    'assignee': assignee,
                    'expires': _now() + datetime.timedelta(seconds=duration),
                    'image_id': image_id,
                    'boot_config': json.dumps(boot_config),
                    'state': 'new',
                    'state_counters': '{}'}

        res = self.db.execute(model.requests.insert(), request)
        return res.lastrowid

    def renew(self, request_id, duration, _now=datetime.datetime.utcnow):
        q = model.requests.update()
        q = q.where(model.requests.c.id==request_id)
        self.db.execute(q,
            dict(expires=_now() + datetime.timedelta(seconds=duration)))

    def list_expired(self, imaging_server_id, _now=datetime.datetime.utcnow):
        """
        Get a list of all requests whose 'expires' timestamp is in the past,
        are not in the 'closed' state or failed, and which belong to this
        imaging server.
        """
        res = self.db.execute(select(
                [model.requests.c.id],
                (model.requests.c.expires < _now())
                & (model.requests.c.state != 'closed')
                & not_(model.requests.c.state.like('failed_%'))
                & (model.requests.c.imaging_server_id == imaging_server_id)))
        return self.column(res)

    def get_imaging_server(self, request_id):
        """
        Get the name of the imaging server associated with this request.
        Raises NotFound if no such request exists.
        """
        res = self.db.execute(select([model.imaging_servers.c.fqdn],
                                            from_obj=[model.requests.join(model.imaging_servers)]).where(model.requests.c.id == request_id))
        return self.singleton(res)

    def list(self, include_closed=False):
        """
        List all open requests (those without state='closed'), or all requests
        if include_closed is true.

        Returns a list of dictionaries, each with keys id, imaging_server,
        assignee, boot_config, state, expires, requested_device, environment,
        assigned_device, and device_state.  The last two are set to the empty
        string if no device is assigned.
        """
        requests = model.requests
        stmt = sqlalchemy.select(
            [requests.c.id,
            model.imaging_servers.c.fqdn.label('imaging_server'),
            requests.c.assignee, requests.c.boot_config, requests.c.state,
            requests.c.expires, requests.c.requested_device,
            requests.c.environment],
            from_obj=[requests.join(model.imaging_servers)])
        if not include_closed:
            stmt = stmt.where(requests.c.state!='closed')
        res = self.db.execute(stmt)
        requests = [dict(row) for row in res]
        res = self.db.execute(sqlalchemy.select([model.device_requests.c.request_id,
                                            model.devices.c.name,
                                            model.devices.c.state],
                                            from_obj=[model.device_requests.join(model.devices)]))
        device_requests = dict([(x[0], (x[1], x[2])) for x in res])
        for r in requests:
            if r['id'] in device_requests:
                r[u'assigned_device'] = device_requests[r['id']][0]
                r[u'device_state'] = device_requests[r['id']][1]
            else:
                r[u'assigned_device'] = u''
                r[u'device_state'] = u''
        return requests

    def get_assigned_device(self, request_id):
        """
        Get the name of the device assigned to this request, or None if no
        device is assigned (or if no such request exists).
        """
        res = self.db.execute(select(
                [model.devices.c.name],
                from_obj=[model.device_requests.join(model.devices)]).where(
                model.device_requests.c.request_id==request_id))
        return self.singleton(res, missing_ok=True)

    def get_info(self, request_id):
        """
        Get useful information about the given request.  The return value is a
        dictionary with keys

          - id
          - requested_device -- device name
          - assignee
          - expires
          - environment
          - image
          - boot_config
          - assigned_device -- device name or empty string

        Raises NotFound if no such request exists.
        """
        res = self.db.execute(select([model.requests.c.requested_device,
                                model.requests.c.assignee,
                                model.requests.c.expires,
                                model.requests.c.environment,
                                model.images.c.name.label('image'),
                                model.requests.c.boot_config],
                                model.requests.c.id==request_id,
                                from_obj=[model.requests.join(model.images)]))
        row = res.fetchone()
        if row is None:
            raise exceptions.NotFound

        request = {'id': request_id,
                'requested_device': row[0],
                'assignee': row[1],
                'expires': row[2],
                'environment': row[3],
                'image': row[4],
                'boot_config': row[5],
                'assigned_device': ''}

        assigned_device = self.db.requests.get_assigned_device(request_id)
        if assigned_device:
            request['assigned_device'] = assigned_device
        return request
