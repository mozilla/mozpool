# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import sqlalchemy
from sqlalchemy.sql import and_
from mozpool.db import model, base

class Methods(base.MethodsBase):

    def dump_devices(self):
        """
        Dump device data.  This returns a list of dictionaries with keys id, name,
        fqdn, inventory_id, mac_address, imaging_server, relay_info, and state.
        Zero or more device names should be passed in as positional arguments.  If
        none are given, dumps all device data.
        """
        devices = model.devices
        img_svrs = model.imaging_servers
        hw_types = model.hardware_types
        stmt = sqlalchemy.select(
            [devices.c.id, devices.c.name, devices.c.fqdn, devices.c.inventory_id,
            devices.c.mac_address, img_svrs.c.fqdn.label('imaging_server'),
            devices.c.relay_info, hw_types.c.type.label('hardware_type'),
            hw_types.c.model.label('hardware_model')],
            from_obj=[devices.join(img_svrs).join(hw_types)])
        res = self.db.execute(stmt)
        return self.dict_list(res)

    def insert_device(self, values, _now=None):
        """Insert a new device into the DB.  VALUES should be in the dictionary
        format used for inventorysync - see inventorysync.py"""
        values = values.copy()

        # convert imaging_server to its ID, and add a default state and counters
        values['imaging_server_id'] = self._find_imaging_server_id(values.pop('imaging_server'))
        values['hardware_type_id'] = self._find_hardware_type_id(
            values.pop('hardware_type'), values.pop('hardware_model'))
        # set up the state machine in the 'new' state, with an immediate timeout
        values['state'] = 'new'
        values['state_timeout'] = _now or datetime.datetime.now()
        values['state_counters'] = '{}'

        self.db.execute(model.devices.insert(), [ values ])

    def delete_device(self, id):
        """Delete the device with the given ID"""
        # foreign keys don't automatically delete log entries, so do it manually.
        # This table is partitioned, so there's no need to later optimize these
        # deletes - they'll get flushed when their parititon is dropped.
        self.db.devices.delete_all_logs(id)
        self.db.execute(model.devices.delete(whereclause=(model.devices.c.id==id)))

    def update_device(self, id, values):
        """Update an existing device with id ID into the DB.  VALUES should be in
        the dictionary format used for inventorysync - see inventorysync.py"""
        values = values.copy()

        # convert imaging_server to its ID, and strip the id
        values['imaging_server_id'] = self._find_imaging_server_id(values.pop('imaging_server'))
        if 'hardware_type' in values or 'hardware_model' in values:
            values['hardware_type_id'] = self._find_hardware_type_id(
                values.pop('hardware_type'), values.pop('hardware_model'))
        if 'id' in values:
            values.pop('id')

        self.db.execute(model.devices.update(whereclause=(model.devices.c.id==id)), **values)

    def dump_relays(self):
        """
        Dump relay_board data from DB.  This returns a list of dictionaries with keys id, name,
        fqdn, and imaging server.
        """
        relay_boards = model.relay_boards
        img_svrs = model.imaging_servers
        stmt = sqlalchemy.select(
            [relay_boards.c.id, relay_boards.c.name, relay_boards.c.fqdn,
            img_svrs.c.fqdn.label('imaging_server')],
            from_obj=[relay_boards.join(img_svrs)])
        res = self.db.execute(stmt)
        return self.dict_list(res)

    def insert_relay_board(self, values, _now=None):
        """Insert a new relay_board into the DB.  VALUES should be in the dictionary
        format used for inventorysync - see inventorysync.py"""
        values = values.copy()

        # convert imaging_server to its ID, and add a default state and counters
        values['imaging_server_id'] = self._find_imaging_server_id(values.pop('imaging_server'))
        values['state'] = 'ready'
        values['state_timeout'] = _now or datetime.datetime.now()
        values['state_counters'] = '{}'

        self.db.execute(model.relay_boards.insert(), [ values ])

    def delete_relay_board(self, id):
        """Delete the relay_board with the given ID"""
        self.db.execute(model.relay_boards.delete(whereclause=(model.relay_boards.c.id==id)))

    def update_relay_board(self, id, values):
        """Update an existing relay_board with ID into the DB.  VALUES should be in
        the dictionary format used for inventorysync - see inventorysync.py"""
        values = values.copy()

        # convert imaging_server to its ID, and strip the id
        values['imaging_server_id'] = self._find_imaging_server_id(values.pop('imaging_server'))
        if 'id' in values:
            values.pop('id')

        self.db.execute(model.relay_boards.update(whereclause=(model.relay_boards.c.id==id)), **values)

    # utility methods

    def _find_imaging_server_id(self, name):
        # try inserting, ignoring failures (most likely due to duplicate row)
        try:
            self.db.execute(model.imaging_servers.insert(),
                fqdn=name)
        except sqlalchemy.exc.SQLAlchemyError:
            pass # probably already exists

        res = self.db.execute(sqlalchemy.select([ model.imaging_servers.c.id ],
                            whereclause=(model.imaging_servers.c.fqdn==name)))
        return self.singleton(res)

    def _find_hardware_type_id(self, hardware_type, hardware_model):

        # try inserting, ignoring failures (most likely due to duplicate row)
        try:
            self.db.execute(model.hardware_types.insert(), type=hardware_type,
                        model=hardware_model)
        except sqlalchemy.exc.SQLAlchemyError:
            pass # probably already exists

        res = self.db.execute(sqlalchemy.select(
                [ model.hardware_types.c.id ],
                and_(model.hardware_types.c.type==hardware_type,
                    model.hardware_types.c.model==hardware_model)))
        return self.singleton(res)

