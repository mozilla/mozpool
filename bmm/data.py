# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import socket
import datetime
import sqlalchemy
from sqlalchemy.sql import select
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
        engine = sqlalchemy.create_engine(config.db_engine())
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

def list_boards_for_imaging_server(server):
    """
    Get the list of boards associated with an imaging server.
    Returns a dict whose 'boards' entry is the list of boards.
    """
    conn = get_conn()
    res = conn.execute(select([model.imaging_servers],
                              model.imaging_servers.c.fqdn==server))
    if res.fetchone() is None:
        raise NotFound
    res = conn.execute(select([model.boards.c.name],
                              from_obj=[model.boards.join(model.imaging_servers, model.imaging_servers.c.fqdn == server)]))
    return {'boards': [row[0].encode('utf-8') for row in res]}

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
    row = res.fetchone()
    return {'state': row['status'].encode('utf-8'),
            #TODO: fetch logs
            'log': []}

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
    config = {}
    if row:
        config = row['boot_config'].encode('utf-8')
    return {'config': config}

def set_board_config(board, config):
    """
    Set the config parameters for the /boot/ API for board.
    """
    get_conn().execute(model.boards.update().
                       where(model.boards.c.name==board).
                       values(boot_config=json.dumps(config)))
    return config

def board_relay_info(board):
    res = get_conn().execute(select([model.boards.c.relay_info],
                                    model.boards.c.name==board))
    info = res.fetchone()[0]
    hostname, bank, relay = info.split(":", 2)
    assert bank.startswith("bank") and relay.startswith("relay")
    return hostname, int(bank[4:]), int(relay[5:])

def add_log(board, message):
    conn = get_conn()
    id = conn.execute(select([model.boards.c.id],
                              model.boards.c.name==board)).fetchone()[0]
    conn.execute(model.logs.insert(),
                 board_id=id,
                 ts=datetime.datetime.now(),
                 source="webapp",
                 message=message)

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
