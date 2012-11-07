# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy
from mozpool import config
import threading

# global for convenience
engine = None

def _checkout_listener(dbapi_con, con_record, con_proxy):
    try:
        cursor = dbapi_con.cursor()
        cursor.execute("SELECT 1")
    except dbapi_con.OperationalError, ex:
        if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
            raise sqlalchemy.exc.DisconnectionError()
        raise

_get_engine_lock = threading.Lock()
def get_engine():
    """
    Get a database engine object.
    """
    with _get_engine_lock:
        global engine
        if engine is None:
            engine_url = config.get('database', 'engine')

            # optimistically recycle connections after 10m
            engine = sqlalchemy.create_engine(engine_url, pool_recycle=600)
            # and pessimistically check connections before using them
            sqlalchemy.event.listen(engine.pool, 'checkout', _checkout_listener)

            # set sqlite to WAL mode to avoid weird concurrency issues
            if engine.dialect.name == 'sqlite':
                try:
                    engine.execute("pragma journal_mode = wal")
                except:
                    pass # oh well..

        return engine

def get_conn():
    """
    Get a database connection object.
    """
    return get_engine().connect()
