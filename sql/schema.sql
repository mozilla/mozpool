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

DROP TABLE IF EXISTS imaging_servers;
CREATE TABLE imaging_servers (
  id integer UNSIGNED not null primary key auto_increment,
  -- fqdn of imaging server
  fqdn varchar(255) not null,

  unique index fqdn_idx (fqdn)
);

DROP TABLE IF EXISTS pxe_configs;
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

DROP TABLE IF EXISTS devices;
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
  -- last PXE config set up for this device
  last_pxe_config_id integer unsigned,
  foreign key (last_pxe_config_id) references pxe_configs(id) on delete restrict,
  -- config the device will use on its next boot (JSON blob)
  boot_config text,
  -- free-form comments about the device (for BMM + Lifeguard)
  comments text,

  unique index name_idx (name),
  index state_timeout_idx (state_timeout)
);

DROP TABLE IF EXISTS requests;
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
  -- config to pass to device once assigned (JSON blob)
  boot_config text,
  -- state machine variables
  state varchar(32) not null,
  state_counters text not null,
  state_timeout datetime
);

DROP TABLE IF EXISTS device_requests;
CREATE TABLE device_requests (
  request_id bigint not null references requests.id on delete restrict,
  device_id integer not null references devices.id on delete restrict,
  unique index request_id_idx (request_id),
  unique index device_id_idx (device_id)
);

DROP TABLE IF EXISTS device_logs;
CREATE TABLE device_logs (
    -- foreign key for the device
    device_id integer not null,
    ts timestamp not null,
    -- short string giving the origin of the message (syslog, api, etc.)
    source varchar(32) not null,
    -- the message itself
    message text not null,
    -- indices
    index device_id_idx (device_id),
    index ts_idx (ts)
);
CALL init_log_partitions('device_logs', 14, 1);

DROP TABLE IF EXISTS request_logs;
CREATE TABLE request_logs (
    -- request this log is for
    request_id bigint not null,
    ts timestamp not null,
    -- short string giving the origin of the message (syslog, api, etc.)
    source varchar(32) not null,
    -- the message itself
    message text not null,
    -- indices
    index request_id_idx (request_id),
    index ts_idx (ts)
);
CALL init_log_partitions('request_logs', 14, 1);


--
-- Events
--

DELIMITER $$

-- and then update every day (this can't be set up in init_log_partitions)
DROP EVENT IF EXISTS update_log_partitions $$
CREATE EVENT update_log_partitions  ON SCHEDULE EVERY 1 day
DO BEGIN
    CALL update_log_partitions('device_logs', 14, 1);
    CALL update_log_partitions('request_logs', 14, 1);
    -- TODO: optimize requests and any other tables that get lots of deletes
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
