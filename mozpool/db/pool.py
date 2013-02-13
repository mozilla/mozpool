# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import socket
import sqlalchemy
import logging

logger = logging.getLogger('db.pool')

# checkout listener, to make sure each connection is still
# good when it's checked out

def _checkout_listener(dbapi_con, con_record, con_proxy):
    try:
        cursor = dbapi_con.cursor()
        cursor.execute("SELECT 1")
    except dbapi_con.OperationalError, ex: # pragma: no cover
        if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
            raise sqlalchemy.exc.DisconnectionError()
        raise

# mysql connect listeners

def _pymysql_connect_listener(dbapi_con, connection_record):
    # apply SO_KEEPALIVE to the socket.
    # see https://github.com/petehunt/PyMySQL/issues/139
    # and https://bugzilla.mozilla.org/show_bug.cgi?id=817762
    sock = dbapi_con.socket
    logger.debug("setting SO_KEEPALIVE on MySQL socket %d" % sock.fileno())
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

# NOTE: the mysqldb driver sets SO_KEEPALIVE itself; no need to do so here

class DBPool(object):

    def __init__(self, db_url):
        self.db_url = db_url

        # optimistically recycle connections after 10m
        engine = self.engine = sqlalchemy.create_engine(db_url, pool_recycle=600)
        # and pessimistically check connections before using them
        sqlalchemy.event.listen(engine.pool, 'checkout', _checkout_listener)

        # set sqlite to WAL mode to avoid weird concurrency issues
        if engine.dialect.name == 'sqlite':
            try:
                engine.execute("pragma journal_mode = wal")
            except: # pragma: no cover
                pass # oh well..

        if engine.dialect.name == 'mysql':
            driver = self.engine.driver
            listener = globals().get("_%s_connect_listener" % driver)
            if listener:
                sqlalchemy.event.listen(engine.pool, 'connect', listener)

    def execute(self, statement, *args, **kwargs):
        """
        Execute the given sqlalchemy statement.

        This method is best accessed as an attribute of the DB object:
        `self.db.execute`
        """
        conn = self.engine.connect()
        return conn.execute(statement, *args, **kwargs)
