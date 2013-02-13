# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import sqlalchemy
from sqlalchemy.sql import select
from mozpool.db import exceptions

class MethodsBase(object):

    def __init__(self, db):
        self.db = db

    # utility methods

    def singleton(self, res, missing_ok=False):
        """
        Return the single column of the single row in ResultProxy res.  This
        raises NotFound if no rows were returned, unless missing_ok is true,
        in which case it returns None
        """
        row = res.first()
        if not row:
            if missing_ok:
                return None
            raise exceptions.NotFound
        return row[0]

    def column(self, res):
        """
        Given a ResultProxy with a set of one-column rows, return a list of the
        values in those rows
        """
        return [row[0] for row in res.fetchall()]

    def dict_list(self, res):
        """
        Given a ResultProxy with a set of multi-column rows, return a list of the
        rows, each represented as a dictionary
        """
        return [dict(row) for row in res.fetchall()]


class StateMachineMethodsMixin(object):

    # The table must have columns 'state', 'state_counters', 'state_timeout',
    # and 'imaging_server_id', as well as an id column by which to look up
    # machines.  Set these in the subclass.

    state_machine_table = None
    state_machine_id_column = None

    def get_machine_state(self, id):
        """
        Get the state of this object, or raise NotFound
        """
        tbl = self.state_machine_table
        res = self.db.execute(select([tbl.c.state],
                            self.state_machine_id_column==id))
        return self.singleton(res)

    def set_machine_state(self, id, state, timeout):
        """
        Set the machine state -- state name and timeout -- of this object,
        without affecting counters
        """
        self.db.execute(self.state_machine_table.update().
                            where(self.state_machine_id_column==id).
                            values(state=state, state_timeout=timeout))

    def get_counters(self, id):
        """
        Get the counters for this machine, or raise NotFound
        """
        tbl = self.state_machine_table
        res = self.db.execute(select([tbl.c.state_counters],
                                self.state_machine_id_column==id))
        return json.loads(self.singleton(res) or '{}')

    def set_counters(self, id, counters):
        """
        Set the counters for this machine
        """
        self.db.execute(self.state_machine_table.update().
                            where(self.state_machine_id_column==id).
                            values(state_counters=json.dumps(counters)))

    def list_timed_out(self, imaging_server_id):
        """
        Get a list of all machine ids whose timeout is in the past, and which
        belong to this imaging server.
        """
        now = datetime.datetime.now()
        tbl = self.state_machine_table
        res = self.db.execute(select(
                [self.state_machine_id_column],
                (tbl.c.state_timeout < now)
                & (tbl.c.imaging_server_id == imaging_server_id)))
        timed_out = [r[0] for r in res.fetchall()]
        return timed_out


class ObjectLogsMethodsMixin(object):

    # Subclasses should set these.  Foreign_key_col is the column in
    # logs_table containing the object id
    logs_table = None
    foreign_key_col = None

    # and override this to convert a name into an ID
    def _get_object_id(self, object_name):
        raise NotImplementedError

    def log_message(self, object_name, message, source="webapp",
            _now=datetime.datetime.now):
        """
        Add a log message for this object.
        """
        id = self._get_object_id(object_name)
        values = {self.foreign_key_col.name: id,
                  "ts": _now(),
                  "source": source,
                  "message": message}
        self.db.execute(self.logs_table.insert(), values)

    def delete_all_logs(self, object_id):
        """
        Delete all log entries for the given object ID.  Note that this method
        does not take an object name.
        """
        self.db.execute(self.logs_table.delete().where(self.foreign_key_col==object_id))

    def get_logs(self, object_name, timeperiod=None, limit=None):
        """
        Get log entries for an object for the past timeperiod, limiting to the
        LIMIT most recent.  Each log entry is represented as a dictionary with
        keys 'id', 'timestamp', 'source', and 'message'.  The timestamp is
        an ISO-format string, not a datetime.
        """

        q = select([self.logs_table.c.id,
                    self.logs_table.c.ts,
                    self.logs_table.c.source,
                    self.logs_table.c.message])
        q = q.order_by(sqlalchemy.desc(self.logs_table.c.ts))
        if timeperiod:
            from_time = datetime.datetime.now() - timeperiod
            q = q.where(self.logs_table.c.ts>=from_time)
        if limit:
            q = q.limit(limit)
        id = self._get_object_id(object_name)
        q = q.where(self.foreign_key_col==id)

        res = self.db.execute(q)
        rv = [{"id": row['id'],
               "timestamp": row["ts"].isoformat(),
               "source": row["source"],
               "message": row["message"]}
              for row in res]
        rv.reverse()
        return rv
