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
_inventory_url = None
_inventory_username = None
_inventory_password = None

def read_config(path):
    """
    Read configuration file from path.
    """
    global config_read, _db_engine, _inventory_url, _inventory_password, _inventory_username
    config = ConfigParser.ConfigParser()
    config.read(path)
    _db_engine = config.get('database', 'engine')
    _inventory_url = config.get('inventory', 'url')
    _inventory_username = config.get('inventory', 'username')
    _inventory_password = config.get('inventory', 'password')
    config_read = True

def set_config(db_engine=None, inventory_url=None, inventory_username=None, inventory_password=None):
    """
    Set configuration parameters directly.
    """
    global config_read, _db_engine, _inventory_url, _inventory_password, _inventory_username
    _db_engine = db_engine
    _inventory_url = inventory_url
    _inventory_username = inventory_username
    _inventory_password = inventory_password
    config_read = True

def db_engine():
    global _db_engine
    if not config_read:
        read_config(os.path.join(os.path.dirname(__file__), "config.ini"))
    return _db_engine

def inventory_url():
    global _db_engine
    if not config_read:
        read_config(os.path.join(os.path.dirname(__file__), "config.ini"))
    return _inventory_url

def inventory_username():
    global _db_engine
    if not config_read:
        read_config(os.path.join(os.path.dirname(__file__), "config.ini"))
    return _inventory_username

def inventory_password():
    global _db_engine
    if not config_read:
        read_config(os.path.join(os.path.dirname(__file__), "config.ini"))
    return _inventory_password

