# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
from mozpool.db import model, sql
from sqlalchemy.sql import and_, select
from sqlalchemy import desc


class Logs(object):
    
    """Abstraction for log tables.
    Each log table is associated with objects described in another table, e.g.
    requests. In the base class, the name of the object is equal to its id.
    """

    def __init__(self, logs_table, object_table, foreign_key_col):
        self.logs_table = logs_table
        self.object_table = object_table
        self.foreign_key_col = foreign_key_col

    def _get_object_id(self, object_name):
        return object_name

    def add(self, name, message, source="webapp"):
        conn = sql.get_conn()
        values = {self.foreign_key_col.name: self._get_object_id(name),
                  "ts": datetime.datetime.now(),
                  "source": source,
                  "message": message}
        conn.execute(self.logs_table.insert(), values)

    def delete_all(self, object_id):
        sql.get_conn().execute(self.logs_table.delete().where(self.foreign_key_col==object_id))

    def log_row_to_dict(self, row):
        return {"id": row['id'],
                "timestamp": row["ts"].isoformat(),
                "source": row["source"],
                "message": row["message"]}

    def get(self, name, timeperiod=None, limit=None):
        """Get log entries for a device for the past timeperiod, limiting to the
        LIMIT most recent."""
        q = select([self.logs_table.c.id,
                    self.logs_table.c.ts,
                    self.logs_table.c.source,
                    self.logs_table.c.message])
        q = q.order_by(desc(self.logs_table.c.ts))
        if timeperiod:
            from_time = datetime.datetime.now() - timeperiod
            q = q.where(and_(self.foreign_key_col==self._get_object_id(name),
                            self.logs_table.c.ts>=from_time))
        if limit:
            q = q.limit(limit)

        res = sql.get_conn().execute(q)
        rv = [self.log_row_to_dict(row) for row in res]
        rv.reverse()
        return rv


class LogsByObjectName(Logs):

    """Variety of Logs object indexed by object name instead of id.
    This is a naive implementation that does a separate select to obtain
    the object id instead of doing joins.
    """

    def _get_object_id(self, object_name):
        return sql.get_conn().execute(select([self.object_table.c.id],
                                              self.object_table.c.name==object_name)).fetchone()[0]


device_logs = LogsByObjectName(model.device_logs, model.devices,
                        model.device_logs.c.device_id)
request_logs = Logs(model.request_logs, model.requests,
                    model.request_logs.c.request_id)
