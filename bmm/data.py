# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import sqlalchemy
from sqlalchemy.sql import select
from itertools import izip_longest
from bmm import model
from bmm import config

# global for convenience
engine = None

class NotFound(Exception):
    pass

def get_conn():
    """
    Get a database connection object.
    """
    global engine
    if engine is None:
        engine_url = config.get('database', 'engine')
        engine = sqlalchemy.create_engine(engine_url)
    return engine.connect()

def row_to_dict(row, table, omit_cols=[]):
    """
    Convert a result row to a dict using the schema from table.
    If omit_cols is specified, omit columns whose names are present
    in that list.
    """
    result = {}
    for col in table.c:
        if col.name in omit_cols:
            continue
        coldata = row[col]
        if isinstance(coldata, unicode):
            coldata = coldata.encode('utf-8')
        result[col.name] = coldata
    return result

def list_boards():
    """
    Get the list of all boards known to the system.
    Returns a dict whose 'boards' entry is the list of boards.
    """
    conn = get_conn()
    res = conn.execute(select([model.boards.c.name]))
    return {'boards': [row[0].encode('utf-8') for row in res]}

def dump_boards():
    """
    Dump all boards.  This returns a list of dictionaries with keys id, name,
    fqdn, invenetory_id, mac_address, imaging_server, relay_info, and status.
    """
    conn = get_conn()
    boards = model.boards
    img_svrs = model.imaging_servers
    res = conn.execute(sqlalchemy.select(
        [ boards.c.id, boards.c.name, boards.c.fqdn, boards.c.inventory_id, boards.c.mac_address,
          img_svrs.c.fqdn.label('imaging_server'), boards.c.relay_info, boards.c.status ],
        from_obj=[boards.join(img_svrs)]))
    return [ dict(row) for row in res ]

def find_imaging_server_id(name):
    """Given an imaging server name, either return the existing ID, or a new ID."""
    conn = get_conn()

    # try inserting, ignoring failures (most likely due to duplicate row)
    try:
        conn.execute(model.imaging_servers.insert(),
            fqdn=name)
    except sqlalchemy.exc.SQLAlchemyError:
        pass # probably already exists

    res = conn.execute(sqlalchemy.select([ model.imaging_servers.c.id ],
                        whereclause=(model.imaging_servers.c.fqdn==name)))
    return res.fetchall()[0].id

def insert_board(values):
    """Insert a new board into the DB.  VALUES should be in the dictionary
    format used for inventorysync - see inventorysync.py"""
    values = values.copy()

    # convert imaging_server to its ID, and add a default status
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    values['status'] = 'new'

    get_conn().execute(model.boards.insert(), [ values ])

def delete_board(id):
    """Delete the board with the given ID"""
    conn = get_conn()
    # foreign keys don't automatically delete log entries, so do it manually.
    # This table is partitioned, so there's no need to later optimize these
    # deletes - they'll get flushed when their parititon is dropped.
    conn.execute(model.logs.delete(), whereclause=(model.logs.c.board_id==id))
    conn.execute(model.boards.delete(), whereclause=(model.boards.c.id==id))

def update_board(id, values):
    """Update an existing board with id ID into the DB.  VALUES should be in
    the dictionary format used for inventorysync - see inventorysync.py"""
    values = values.copy()

    # convert imaging_server to its ID, and add a default status
    values['imaging_server_id'] = find_imaging_server_id(values.pop('imaging_server'))
    if 'id' in values:
        values.pop('id')

    get_conn().execute(model.boards.update(whereclause=(model.boards.c.id==id)), **values)

def get_server_for_board(board):
    """
    Get the name of the imaging server associated with this board.
    """
    res = get_conn().execute(select([model.imaging_servers.c.fqdn],
                                    from_obj=[model.boards.join(model.imaging_servers)]).where(model.boards.c.name == board))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return row[0].encode('utf-8')

# The rest of the board methods should not have to check for a valid board.
# Handler methods will check before calling.
def board_status(board):
    """
    Get the status of board.
    """
    res = get_conn().execute(select([model.boards.c.status],
                                    model.boards.c.name==board))
    row = res.fetchall()[0]
    return {"status": row['status'].encode('utf-8'),
            "log": get_logs(board)}

def set_board_status(board, status):
    """
    Set the status of board to status.
    """
    get_conn().execute(model.boards.update().
                       where(model.boards.c.name==board).
                       values(status=status))
    return status

def board_config(board):
    """
    Get the config parameters passed to the /boot/ API for board.
    """
    res = get_conn().execute(select([model.boards.c.boot_config],
                                    model.boards.c.name==board))
    row = res.fetchone()
    config_data = {}
    if row:
        config_data = json.loads(row['boot_config'].encode('utf-8'))
    return {'config': config_data}

def set_board_config(board, config_data):
    """
    Set the config parameters for the /boot/ API for board.
    """
    get_conn().execute(model.boards.update().
                       where(model.boards.c.name==board).
                       values(boot_config=json.dumps(config_data)))
    return config

def board_relay_info(board):
    res = get_conn().execute(select([model.boards.c.relay_info],
                                    model.boards.c.name==board))
    info = res.fetchone()[0]
    hostname, bank, relay = info.split(":", 2)
    assert bank.startswith("bank") and relay.startswith("relay")
    return hostname, int(bank[4:]), int(relay[5:])

def mac_with_dashes(mac):
    """
    Reformat a 12-digit MAC address to contain
    a dash between each 2 characters.
    """
    # From the itertools docs.
    return "-".join("%s%s" % i for i in izip_longest(fillvalue=None, *[iter(mac)]*2))

def board_mac_address(board):
    """
    Get the mac address of board.
    """
    res = get_conn().execute(select([model.boards.c.mac_address],
                                    model.boards.c.name==board))
    row = res.fetchone()
    return row['mac_address'].encode('utf-8')

def add_log(board, message):
    conn = get_conn()
    board_id = conn.execute(select([model.boards.c.id],
                                   model.boards.c.name==board)).fetchone()[0]
    conn.execute(model.logs.insert(),
                 board_id=board_id,
                 ts=datetime.datetime.utcnow(),
                 source="webapp",
                 message=message)

def get_logs(board, timeperiod=datetime.timedelta(hours=1)):
    """Get log entries for a board for the past timeperiod."""
    then = datetime.datetime.utcnow() - timeperiod
    res = get_conn().execute(select([model.logs.c.ts,
                                     model.logs.c.source,
                                     model.logs.c.message],
                                    from_obj=[model.boards.join(model.logs,
                                                                model.boards.c.id == model.logs.c.board_id)]).where(model.boards.c.name == board))
    return [{"timestamp": row["ts"].isoformat(),
             "source": row["source"],
             "message": row["message"]} for row in res]

def list_bootimages():
    conn = get_conn()
    res = conn.execute(select([model.images.c.name]))
    return {'bootimages': [row[0].encode('utf-8') for row in res]}

def bootimage_details(image):
    conn = get_conn()
    res = conn.execute(select([model.images],
                              model.images.c.name==image))
    row = res.fetchone()
    if row is None:
        raise NotFound
    return {'details': row_to_dict(row, model.images, omit_cols=['id'])}

# bmm-model script
def bmm_model():
    engine_url = config.get('database', 'engine')
    engine = sqlalchemy.create_engine(engine_url)
    model.metadata.create_all(bind=engine)
