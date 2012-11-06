# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sqlalchemy
from mozpool import config

# global for convenience
engine = None

def get_engine():
    """
    Get a database engine object.
    """
    global engine
    if engine is None:
        engine_url = config.get('database', 'engine')
        engine = sqlalchemy.create_engine(engine_url)
    return engine

def get_conn():
    """
    Get a database connection object.
    """
    return get_engine().connect()
