# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import ConfigParser

__all__ = [
    'read_config',
    'set_config',
    'db_engine',
    ]

config_read = False
_db_engine = None

def read_config(path):
    """
    Read configuration file from path.
    """
    global config_read, _db_engine
    config = ConfigParser.ConfigParser()
    config.read(path)
    _db_engine = config.get('database', 'engine')
    config_read = True

def set_config(db_engine=None):
    """
    Set configuration parameters directly.
    """
    global config_read, _db_engine
    _db_engine = db_engine
    config_read = True

def db_engine():
    global _db_engine
    if not config_read:
        read_config(os.path.join(os.path.dirname(__file__), "config.ini"))
    return _db_engine
