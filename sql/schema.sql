--
-- automated log partition handling
--

DELIMITER $$

-- Procedure to initialize partitioning on the log tables
DROP PROCEDURE IF EXISTS init_log_partitions $$
CREATE PROCEDURE init_log_partitions(log_table_name TEXT, days_past INT, days_future INT)
BEGIN
    DECLARE newpart integer;
    SELECT UNIX_TIMESTAMP(NOW()) INTO newpart;
    SELECT newpart - (newpart % 86400) INTO newpart; -- round down to the previous whole day

    -- add partitions, with a single partition for the beginning of the current day, then
    -- let update_log_partitions take it from there
    -- SELECT CONCAT('initial partition ', CAST(newpart as char(16)), ' for table ', log_table_name);
    SET @sql := CONCAT('ALTER TABLE ', log_table_name, ' PARTITION BY RANGE (UNIX_TIMESTAMP(ts)) ('
                        , 'PARTITION p'
                        , CAST(newpart as char(16))
                        , ' VALUES LESS THAN ('
                        , CAST(newpart as char(16))
                        , '));');
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    -- do an initial update to get things synchronized
    call update_log_partitions(log_table_name, days_past, days_future);
END $$

-- Procedure to delete old partitions and create new ones around the current date
DROP PROCEDURE IF EXISTS update_log_partitions $$
CREATE PROCEDURE update_log_partitions(log_table_name TEXT, days_past INT, days_future INT)
BEGIN
    DECLARE part integer;
    DECLARE newpart integer;
    DECLARE earliest integer;
    DECLARE latest integer;

    -- add new partitions; keep adding a partition for a new day until we reach latest
    SELECT UNIX_TIMESTAMP(NOW()) + 86400 * (days_future+1) INTO latest;
    createloop: LOOP
        -- Get the newest partition (PARTITION_DESCRIPTION is the number from VALUES LESS THAN)
        -- partitions are named similarly, with a 'p' prefix
        SELECT MAX(PARTITION_DESCRIPTION) INTO part
            FROM INFORMATION_SCHEMA.PARTITIONS
            WHERE TABLE_NAME=log_table_name
            AND TABLE_SCHEMA='mozpool';
        IF part < latest THEN -- note part cannot be NULL, as there must be at least one partition
            SELECT part + 86400 INTO newpart;
            -- SELECT CONCAT('add partition ', CAST(newpart as CHAR(16)), ' to ', log_table_name);
            SET @sql := CONCAT('ALTER TABLE ', log_table_name, ' ADD PARTITION ( PARTITION p'
                                , CAST(newpart as char(16))
                                , ' VALUES LESS THAN ('
                                , CAST(newpart as char(16))
                                , '));');
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
        ELSE
            LEAVE createloop;
        END IF;
    END LOOP;

    -- now, deal with pruning old partitions; select the minimum partition
    -- and delete it if it's too old
    SELECT UNIX_TIMESTAMP(NOW()) - 86400 * (days_past+1) INTO earliest;
    purgeloop: LOOP
        -- Get the oldest partition
        SELECT MIN(PARTITION_DESCRIPTION) INTO part
            FROM INFORMATION_SCHEMA.PARTITIONS
            WHERE TABLE_NAME=log_table_name
            AND TABLE_SCHEMA='mozpool';
        IF part < earliest THEN
            -- SELECT CONCAT('drop partition ', CAST(part as CHAR(16)), ' to ', log_table_name);
            SET @sql := CONCAT('ALTER TABLE ', log_table_name, ' DROP PARTITION p'
                                , CAST(part as char(16))
                                , ';');
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
        ELSE
            LEAVE purgeloop;
        END IF;
    END LOOP;
END $$

DELIMITER ;

--
-- Tables
--

DROP TABLE IF EXISTS device_requests;
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS requests;
DROP TABLE IF EXISTS imaging_servers;
DROP TABLE IF EXISTS image_pxe_configs;
DROP TABLE IF EXISTS pxe_configs;
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS hardware_types;
DROP TABLE IF EXISTS device_logs;
DROP TABLE IF EXISTS request_logs;

CREATE TABLE imaging_servers (
  id integer UNSIGNED not null primary key auto_increment,
  -- fqdn of imaging server
  fqdn varchar(255) not null,

  unique index fqdn_idx (fqdn)
);

CREATE TABLE pxe_configs (
  id integer unsigned not null primary key auto_increment,
  -- short identifier
  name varchar(32) not null,
  -- version, scoped to the name
  description text not null,
  -- pxe configuration text
  contents TEXT not null,
  -- true (1) if this config should be shown in the web UI
  active INTEGER not null,

  unique index name_idx (name)
);

CREATE TABLE images (
  id integer unsigned not null primary key auto_increment,
  -- short identifier
  name varchar(32) not null,
  -- required boot_config keys (JSON list)
  boot_config_keys text not null,
  -- true (1) if we can reuse an existing device with this image and boot_config
  can_reuse INTEGER not null,
  -- true (1) if this image should be hidden from the user (used for utility images
  -- like self-test, maintenance, etc.)
  hidden INTEGER not null,
  -- true (1) if this image contains a SUT agent available on boot
  has_sut_agent INTEGER not null,

  unique index name_idx (name)
);

CREATE TABLE hardware_types (
  id integer unsigned not null primary key auto_increment,
  -- type of hardware, e.g. panda, tegra, phone, ...
  type varchar(32) not null,
  -- specific model, optional
  model varchar(32) not null,

  unique index typemodel_index (type, model)
);

CREATE TABLE image_pxe_configs (
  image_id integer unsigned not null,
  foreign key (image_id) references images(id) on delete restrict,
  hardware_type_id integer unsigned not null,
  foreign key (hardware_type_id) references hardware_types(id) on delete restrict,
  pxe_config_id integer unsigned,
  foreign key (pxe_config_id) references pxe_configs(id) on delete restrict,

  unique index imagehardware_index (image_id, hardware_type_id),
  primary key pk (image_id, hardware_type_id)
);

CREATE TABLE device_logs (
    id bigint not null auto_increment,
    -- foreign key for the device
    device_id integer not null,
    ts timestamp not null,
    -- short string giving the origin of the message (syslog, api, etc.)
    source varchar(32) not null,
    -- the message itself
    message text not null,
    -- indices
    index device_id_idx (device_id),
    index ts_idx (ts),
    primary key pk (id, ts)
);
CALL init_log_partitions('device_logs', 14, 1);

CREATE TABLE request_logs (
    id bigint not null auto_increment,
    -- request this log is for
    request_id bigint not null,
    ts timestamp not null,
    -- short string giving the origin of the message (syslog, api, etc.)
    source varchar(32) not null,
    -- the message itself
    message text not null,
    -- indices
    index request_id_idx (request_id),
    index ts_idx (ts),
    primary key pk (id, ts)
);
CALL init_log_partitions('request_logs', 14, 1);

CREATE TABLE devices (
  id integer UNSIGNED not null primary key auto_increment,
  -- short name (no dots)
  name varchar(32) not null,
  -- canonical fully-qualified hostname
  fqdn varchar(256) not null,
  -- "foreign key" to the inventory db
  inventory_id integer not null,
  -- state machine variables
  state varchar(32) not null,
  state_counters text not null,
  state_timeout datetime,
  -- lower-case, no colons
  mac_address varchar(12) not null,
  -- fqdn of imaging server
  imaging_server_id integer unsigned not null,
  foreign key (imaging_server_id) references imaging_servers(id) on delete restrict,
  -- path to the device's power relay; format TBD; NULL=no control
  relay_info text,
  -- current image installed on this device, plus boot config (JSON blob)
  image_id integer unsigned,
  foreign key (image_id) references images(id) on delete restrict,
  boot_config text,
  -- current image installed on this device, plus boot config (JSON blob)
  next_image_id integer unsigned,
  foreign key (next_image_id) references images(id) on delete restrict,
  next_boot_config text,
  -- free-form comments about the device (for BMM + Lifeguard)
  comments text,
  -- fields for filtering devices when requesting
  environment varchar(32) not null default 'none',
  -- hardware description
  hardware_type_id integer unsigned,
  foreign key (hardware_type_id) references hardware_types(id) on delete restrict,

  unique index name_idx (name),
  index state_timeout_idx (state_timeout)
);

CREATE TABLE requests (
  id bigint unsigned not null primary key auto_increment,
  -- fqdn of imaging server
  imaging_server_id integer unsigned not null,
  foreign key (imaging_server_id) references imaging_servers(id) on delete restrict,
  -- name of requested device; could be 'any' or a particular device name
  requested_device varchar(32) not null,
  -- short identifier for the requester/assignee
  assignee varchar(256) not null,
  -- time (UTC) at which the request will expire (if not renewed)
  expires datetime not null,
  -- image requested
  image_id integer unsigned not null,
  foreign key (image_id) references images(id) on delete restrict,
  -- config to pass to device once assigned (JSON blob)
  boot_config text,
  -- state machine variables
  state varchar(32) not null,
  state_counters text not null,
  state_timeout datetime,
  -- constraining fields for the request
  environment varchar(32) not null default 'any'
);

CREATE TABLE device_requests (
  request_id bigint not null references requests.id on delete restrict,
  device_id integer not null references devices.id on delete restrict,
  -- the state of the requested device, as filled in by the lifeguard layer.
  imaging_result varchar(32),
  unique index request_id_idx (request_id),
  unique index device_id_idx (device_id)
);


--
-- Maintenance
--

DELIMITER $$

-- and then update every day; this is called by cron on the admin host
DROP PROCEDURE IF EXISTS dbcron $$
CREATE PROCEDURE dbcron()
BEGIN
    CALL update_log_partitions('device_logs', 14, 1);
    CALL update_log_partitions('request_logs', 14, 1);
    -- drop old requests; this interval should be greater than the log retention interval
    DELETE from requests where expires < DATE_SUB(NOW(), INTERVAL 1 WEEK);
    -- optimize the request table, since things are often added and removed
    OPTIMIZE TABLE requests;
END $$

DELIMITER ;

--
-- Log insertion utility (called from rsyslogd)
--

DELIMITER $$

-- Procedure to insert a log entry given a device name.  This silently drops log entries for
-- devices that are not configured.
DROP PROCEDURE IF EXISTS insert_device_log_entry $$
CREATE PROCEDURE insert_device_log_entry(device TEXT, ts TIMESTAMP, source TEXT, message TEXT)
BEGIN
    DECLARE deviceid integer;
    SELECT id from devices where name=device INTO deviceid;
    IF deviceid is not NULL THEN BEGIN
        -- note that we ignore the time specified by the device and just use the current time
        INSERT INTO device_logs (device_id, ts, source, message) values (deviceid, NOW(), source, ltrim(message));
    END;
    END IF;
END $$

DELIMITER ;
