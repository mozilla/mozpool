# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import types
from sqlalchemy.sql import and_, select
from mozpool.db import model, base, exceptions

class Methods(base.MethodsBase,
        base.ObjectLogsMethodsMixin,
        base.StateMachineMethodsMixin):

    state_machine_table = model.devices
    state_machine_id_column = model.devices.c.name

    logs_table = model.device_logs
    foreign_key_col = model.device_logs.c.device_id

    def _get_object_id(self, object_name):
        res = self.db.execute(select([model.devices.c.id],
                            model.devices.c.name==object_name))
        return self.singleton(res)

    def list(self, detail=False):
        """
        Get the list of all devices known to the system.

        If `detail` is True, then each device is represented by a dictionary
        with keys id, name, fqdn, inventory_id, mac_address, imaging_server,
        relay_info, state, image, boot_config, environment, comments, and request_id.

        The `request_id` field is the request attached to the device, or None.
        """
        if detail:
            devices = model.devices
            device_requests = model.device_requests
            img_svrs = model.imaging_servers
            images = model.images
            from_obj = devices.join(img_svrs)
            from_obj = from_obj.outerjoin(images, images.c.id==devices.c.image_id)
            from_obj = from_obj.outerjoin(device_requests, device_requests.c.device_id==devices.c.id)
            stmt = select(
                [devices.c.id, devices.c.name, devices.c.fqdn, devices.c.inventory_id,
                devices.c.mac_address, img_svrs.c.fqdn.label('imaging_server'),
                devices.c.relay_info, devices.c.state, devices.c.comments,
                images.c.name.label('image'), devices.c.boot_config,
                devices.c.environment, device_requests.c.request_id],
                from_obj=[from_obj])
            res = self.db.execute(stmt)
            return self.dict_list(res)
        else:
            res = self.db.execute(select([model.devices.c.name]))
            return self.column(res)

    def list_available(self, device_name='any', environment='any'):
        """
        Get available devices with any other necessary characteristics.  Pass
        'any' for a wildcard.  It's up to the caller to decide if some of
        these devices are better than others (e.g. image already installed).
        "Available" is defined as in the ready state and not attached to an
        existing request.

        This returns a list of dictionaries with keys 'name', 'image', and
        'boot_config'.
        """
        f = model.devices.outerjoin(model.device_requests).outerjoin(
            model.images, model.devices.c.image_id==model.images.c.id)
        q = select([model.devices.c.name, model.devices.c.boot_config,
                    model.images.c.name.label('image')], from_obj=[f])
        # make sure it's free
        q = q.where(model.devices.c.state=="ready")
        # check that there's no matching requests row (using an inner
        # join and expecting NULL)
        q = q.where(model.device_requests.c.request_id == None)
        # other characteristics
        if device_name != 'any':
            q = q.where(model.devices.c.name == device_name)
        if environment != 'any':
            q = q.where(model.devices.c.environment == environment)
        return self.dict_list(self.db.execute(q))

    def list_states(self):
        """
        Get the state of all devices.  Returns a dictionary with device names
        as keys and device states as values.
        """
        res = self.db.execute(select([model.devices.c.name, model.devices.c.state]))
        return { r.name : r.state for r in res.fetchall() }

    def get_fqdn(self, device_name):
        """
        Get the fqdn of the device.
        Raises NotFound if the device is not found.
        """
        res = self.db.execute(select([model.devices.c.fqdn],
                                            model.devices.c.name==device_name))
        return self.singleton(res)

    def get_imaging_server(self, device_name):
        """
        Gets the name of the imaging server associated with this device name.
        Raises NotFound if the device is not found.
        """
        res = self.db.execute(select([model.imaging_servers.c.fqdn],
                                from_obj=[model.devices.join(model.imaging_servers)],
                                whereclause=model.devices.c.name == device_name))
        return self.singleton(res)

    def get_mac_address(self, device_name):
        """
        Get the mac address of device.
        Raises NotFound if the device is not found.
        """
        res = self.db.execute(select([model.devices.c.mac_address],
                                            model.devices.c.name==device_name))
        return self.singleton(res)

    def get_pxe_config(self, device, image=None):
        """
        Get the name of the PXE config to use for this device's hardware type
        and either the specified image or the device's *next* image.  Raises
        NotFound if the device or image is not found, or if no PXE config for
        the hardware type and image combination exists.
        """
        res = self.db.execute(select(
                [model.devices.c.hardware_type_id,
                model.devices.c.next_image_id]).where(
                model.devices.c.name==device))
        row = res.fetchone()
        if row is None:
            raise exceptions.NotFound
        hw_type_id = row[0]
        if not image:
            img_id = row[1]
        else:
            res = self.db.execute(select([model.images.c.id]).where(
                    model.images.c.name==image))
            row = res.fetchone()
            if row is None:
                raise exceptions.NotFound
            img_id = row[0]
        res = self.db.execute(select(
                [model.pxe_configs.c.name],
                from_obj=[model.image_pxe_configs.join(
                        model.pxe_configs)]).where(and_(
                    model.image_pxe_configs.c.hardware_type_id==hw_type_id,
                    model.image_pxe_configs.c.image_id==img_id)))
        return self.singleton(res)

    def has_sut_agent(self, device_name):
        """
        Determine, from the current image on the device, if it has a SUT
        agent.  Raises NotFound if the device is not found.
        """
        res = self.db.execute(select([model.images.c.has_sut_agent],
                from_obj=[model.devices.outerjoin(
                            model.images,
                            model.devices.c.image_id==model.images.c.id)],
                whereclause=(model.devices.c.name==device_name)))
        return self.singleton(res)

    def get_relay_info(self, device_name):
        """
        Get the relay info for the given device, in the form (hostname, bank,
        relay).  Raises NotFound if no such device exists, and returns None if
        no relay is configured for the device.
        """
        res = self.db.execute(select([model.devices.c.relay_info],
                                            model.devices.c.name==device_name))
        val = self.singleton(res)
        if not val:
            # device has no configured relay info
            return None
        hostname, bank, relay = val.rsplit(":", 2)
        assert bank.startswith("bank") and relay.startswith("relay")
        return hostname, int(bank[4:]), int(relay[5:])

    def _get_image(self, image_id_col, boot_config_col, device_name):
        res = self.db.execute(select(
            [boot_config_col.label('boot_config'), model.images.c.name.label('image')],
            from_obj=model.devices.outerjoin(model.images,
                    image_id_col==model.images.c.id),
            whereclause=(model.devices.c.name==device_name)))
        row = res.first()
        if row:
            return dict(row)
        else:
            return {}

    def _set_image(self, image_id_col, boot_config_col, device_name, image_name, boot_config):
        assert isinstance(boot_config, (str, unicode, types.NoneType))
        if image_name:
            res = self.db.execute(select([model.images.c.id]).
                    where(model.images.c.name==image_name))
            image_id = self.singleton(res)
        else:
            image_id = None
        vals = {image_id_col.name: image_id, boot_config_col.name: boot_config}
        self.db.execute(model.devices.update().
                    where(model.devices.c.name==device_name).
                    values(**vals))

    def get_image(self, device_name):
        """
        Get the boot config and current image for this device.  The return value
        is a dictionary with keys 'image' and 'boot_config'.  The boot_config
        is a JSON string.  Both can be None if no known image is installed on this
        device.

        Returns an empty dictionary if the device is not found.
        """
        return self._get_image(model.devices.c.image_id, model.devices.c.boot_config, device_name)

    def set_image(self, device_name, image_name, boot_config):
        """
        Set the named device's image and boot_config.  The boot_config should
        be a JSON string.

        Raises NotFound if there is no such image
        """
        return self._set_image(model.devices.c.image_id, model.devices.c.boot_config,
                device_name, image_name, boot_config)

    def get_next_image(self, device_name):
        """
        Like `get_image`, but get the boot config and next image for this device.
        """
        return self._get_image(model.devices.c.next_image_id, model.devices.c.next_boot_config, device_name)

    def set_next_image(self, device_name, image_name, boot_config):
        """
        Like `set_image`, but set the next image for this device.
        """
        return self._set_image(model.devices.c.next_image_id, model.devices.c.next_boot_config,
                device_name, image_name, boot_config)

    def set_comments(self, device_name, comments):
        """
        Set the comments for the given device.
        """
        self.db.execute(model.devices.update().
                    where(model.devices.c.name==device_name).
                    values(comments=comments))

    def set_environment(self, device_name, environment):
        """
        Set the environment for the given device.
        """
        self.db.execute(model.devices.update().
                    where(model.devices.c.name==device_name).
                    values(environment=environment))
