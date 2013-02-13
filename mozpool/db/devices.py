# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

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
        relay_info, state, last_image, boot_config, environment, and comments.
        """
        if detail:
            devices = model.devices
            img_svrs = model.imaging_servers
            images = model.images
            stmt = select(
                [devices.c.id, devices.c.name, devices.c.fqdn, devices.c.inventory_id,
                devices.c.mac_address, img_svrs.c.fqdn.label('imaging_server'),
                devices.c.relay_info, devices.c.state, devices.c.comments,
                images.c.name.label('last_image'), devices.c.boot_config,
                devices.c.environment],
                from_obj=[devices.join(img_svrs).outerjoin(images)])
            res = self.db.execute(stmt)
            return self.dict_list(res)
        else:
            res = self.db.execute(select([model.devices.c.name]))
            return self.column(res)

    def list_free(self, device_name='any', environment='any'):
        """
        Get available devices with any other necessary characteristics.  Pass
        'any' for a wildcard.  It's up to the caller to decide if some of
        these devices are better than others (e.g. image already installed).

        This returns a list of dictionaries with keys 'name', 'image', and
        'boot_config'.
        """
        f = model.devices.outerjoin(model.device_requests).outerjoin(
            model.images, model.devices.c.last_image_id==model.images.c.id)
        q = select([model.devices.c.name, model.devices.c.boot_config,
                    model.images.c.name.label('image')], from_obj=[f])
        # make sure it's free
        q = q.where(model.devices.c.state=="free")
        # double-check that there's no matching requests row (using an inner
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
        and either the specified image or the device's current image.  Raises
        NotFound if the device or image is not found, or if no PXE config for
        the hardware type and image combination.
        """
        res = self.db.execute(select(
                [model.devices.c.hardware_type_id,
                model.devices.c.last_image_id]).where(
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
        Determine, from the last known image on the device, if it has a SUT
        agent.  Raises NotFound if the device is not found.
        """
        res = self.db.execute(select([model.images.c.has_sut_agent],
                from_obj=[model.devices.outerjoin(
                            model.images,
                            model.devices.c.last_image_id==model.images.c.id)],
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

    def get_image(self, device_name):
        """
        Get the boot config and last image for this device.  The return value
        is a dictionary with keys 'image' and 'boot_config'.  The boot_config
        is a JSON string.

        Returns an empty dictionary if the device is not found.
        """
        res = self.db.execute(select(
            [model.devices.c.boot_config, model.images.c.name.label('image')],
            from_obj=model.devices.outerjoin(model.images,
                    model.devices.c.last_image_id==model.images.c.id),
            whereclause=(model.devices.c.name==device_name)))
        row = res.first()
        if row:
            return dict(row)
        else:
            return {}

    def set_image(self, device_name, image_name, boot_config):
        """
        Set the named device's image and boot_config.  The boot_config should
        be a JSON string.

        Raises NotFound if there is no such image
        """
        assert isinstance(boot_config, (str, unicode))
        res = self.db.execute(select([model.images.c.id]).
                where(model.images.c.name==image_name))
        image_id = self.singleton(res)
        self.db.execute(model.devices.update().
                    where(model.devices.c.name==device_name).
                    values(last_image_id=image_id,
                            boot_config=boot_config))

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
