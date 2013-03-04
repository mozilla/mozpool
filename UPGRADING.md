Next Version
============

Schema Upgrade
--------------

First, find the name of the foreign key relationship for devices.last_image_id,
using `show create table devices`.  In the example below, that's
`devices_ibfk_4`, but may be different elsewhere.

    alter table devices drop foreign key devices_ibfk_4;
    alter table devices change column last_image_id image_id int(10) unsigned;
    alter table devices add foreign key(image_id) references images(id);
    alter table devices add column next_image_id int(10) unsigned;
    alter table devices add foreign key(next_image_id) references images(id);
    alter table devices add column next_boot_config text;
    alter table device_requests add column imaging_result varchar(32);

You will want to move all `free` devices to the `ready` state, and set a timeout for `ready` devices.
After shutting down the old version, execute:

    update devices set state='ready', state_timeout=NOW() where state='free'
