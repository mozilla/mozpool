DROP TABLE IF EXISTS boards;
CREATE TABLE boards (
  id integer UNSIGNED not null primary key auto_increment,
  -- short name (no dots)
  name varchar(32) not null,
  -- canonical fully-qualified hostname
  fqdn varchar(256) not null,
  -- "foreign key" to the inventory db
  inventory_id integer not null,
  -- short descriptive string
  status varchar(32),
  -- lower-case, no colons
  mac_address varchar(10) not null,
  -- fqdn of imaging server
  imaging_server_id integer unsigned not null,
  foreign key (imaging_server_id) references imaging_servers(id) on delete restrict,
  -- path to the board's power relay; format TBD; NULL=no control
  relay_info text,
  -- config the board will use on its next boot (JSON blob)
  boot_config text
);

DROP TABLE IF EXISTS imaging_servers;
CREATE TABLE imaging_servers (
  id integer UNSIGNED not null primary key auto_increment,
  -- fqdn of imaging server
  fqdn varchar(256) not null
);

DROP TABLE IF EXISTS images;
CREATE TABLE images (
  id integer unsigned not null primary key auto_increment,
  -- short identifier
  name varchar(32) not null,
  -- version, scoped to the name
  version integer not null,
  -- larger description of the image; visible on web
  description text not null,
  -- pxe configuration file (absolute path) to use for this image
  pxe_config_filename varchar(256) not null
);

DROP TABLE IF EXISTS logs;
CREATE TABLE logs (
    -- foreign key for the board
    board_id integer not null,
    ts timestamp not null,
    -- short string giving the origin of the message (syslog, api, etc.)
    source varchar(32) not null,
    -- the message itself
    message text not null,
    -- indices
    index board_id_idx (board_id),
    index ts_idx (ts)
);

--
-- automated log partition handling
--

DELIMITER $$

-- Procedure to initialize partitioning on the logs table
DROP PROCEDURE IF EXISTS init_log_partitions $$
CREATE PROCEDURE init_log_partitions(days_past INT, days_future INT)
BEGIN
    DECLARE newpart integer;
    SELECT UNIX_TIMESTAMP(NOW()) INTO newpart;
    SELECT newpart - (newpart % 86400) INTO newpart; -- round down to the previous whole day

    -- add partitions, with a single partition for the beginning of the current day, then
    -- let update_log_partitions take it from there
    SET @sql := CONCAT('ALTER TABLE logs PARTITION BY RANGE (UNIX_TIMESTAMP(ts)) ('
                        , 'PARTITION p'
                        , CAST(newpart as char(16))
                        , ' VALUES LESS THAN ('
                        , CAST(newpart as char(16))
                        , '));');
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    -- do an initial update to get things synchronized
    call update_log_partitions(days_past, days_future);
END $$

-- Procedure to delete old partitions and create new ones around the current date
DROP PROCEDURE IF EXISTS update_log_partitions $$
CREATE PROCEDURE update_log_partitions(days_past INT, days_future INT)
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
            WHERE TABLE_NAME='logs'
            AND TABLE_SCHEMA='black_mobile_magic';
        IF part < latest THEN -- note part cannot be NULL, as there must be at least one partition
            SELECT part + 86400 INTO newpart;
            SET @sql := CONCAT('ALTER TABLE logs ADD PARTITION ( PARTITION p'
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
            WHERE TABLE_NAME='logs'
            AND TABLE_SCHEMA='black_mobile_magic';
        IF part < earliest THEN
            SET @sql := CONCAT('ALTER TABLE logs DROP PARTITION p'
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

-- initialize the partitioning
CALL init_log_partitions(14, 1);

-- and then update every day (this can't be set up in init_log_partitions)
DROP EVENT IF EXISTS update_log_partitions;
CREATE EVENT update_log_partitions  ON SCHEDULE EVERY 1 day
DO CALL update_log_partitions(14, 1);

--
-- Log insertion utility (called from rsyslogd)
--

DELIMITER $$

-- Procedure to insert a log entry given a board name.  This silently drops log entries for
-- boards that are not configured.
DROP PROCEDURE IF EXISTS insert_log_entry $$
CREATE PROCEDURE insert_log_entry(board TEXT, ts TIMESTAMP, source TEXT, message TEXT)
BEGIN
    DECLARE boardid integer;
    SELECT id from boards where name=board INTO boardid;
    IF boardid is not NULL THEN BEGIN
        -- 1526 occurs when there's no matching partition; in this case, use NOW() instead of the timestamp
        DECLARE CONTINUE HANDLER FOR 1526 BEGIN
            INSERT INTO logs (board_id, ts, source, message) values (boardid, NOW(), source, ltrim(message));
        END;
        -- trim the message since rsyslogd prepends a space
        INSERT INTO logs (board_id, ts, source, message) values (boardid, ts, source, ltrim(message));
    END;
    END IF; 
END $$

DELIMITER ;
