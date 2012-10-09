# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import socket
import ConfigParser

__all__ = [
    'read_config',
    'set_config',
    'db_engine',
    'server_fqdn',
    'tftp_root',
    ]

config_read = False
_db_engine = None
_inventory_url = None
_inventory_username = None
_inventory_password = None
_server_fqdn = None
_tftp_root = None
_image_store = None

def read_config(path=os.path.join(os.path.dirname(__file__), "config.ini")):
    """
    Read configuration file from path.
    """
    global config_read, _db_engine, _inventory_url, _inventory_password, _inventory_username, _server_fqdn, _tftp_root, _image_store
    if config_read:
        return
    defaults = {'fqdn': socket.getfqdn()}
    config = ConfigParser.ConfigParser(defaults=defaults)
    config.read(path)
    _db_engine = config.get('database', 'engine')
    _inventory_url = config.get('inventory', 'url')
    _inventory_username = config.get('inventory', 'username')
    _inventory_password = config.get('inventory', 'password')
    _server_fqdn = config.get('server', 'fqdn')
    _tftp_root = config.get('paths', 'tftp_root')
    _image_store = config.get('paths', 'image_store')
    config_read = True

def set_config(db_engine=None,
               inventory_url=None,
               inventory_username=None,
               inventory_password=None,
               server_fqdn=None,
               tftp_root=None,
               image_store=None):
    """
    Set configuration parameters directly.
    """
    global config_read, _db_engine, _inventory_url, _inventory_password, _inventory_username, _server_fqdn, _tftp_root, _image_store
    _db_engine = db_engine
    _inventory_url = inventory_url
    _inventory_username = inventory_username
    _inventory_password = inventory_password
    _server_fqdn = server_fqdn
    _tftp_root = tftp_root
    _image_store = image_store
    config_read = True

def db_engine():
    global _db_engine
    read_config()
    return _db_engine

def inventory_url():
    global _db_engine
    read_config()
    return _inventory_url

def server_fqdn():
    global _server_fqdn
    read_config()
    return _server_fqdn

def inventory_username():
    global _inventory_username
    read_config()
    return _inventory_username

def tftp_root():
    global _tftp_root
    read_config()
    return _tftp_root

def inventory_password():
    global _inventory_password
    read_config()
    return _inventory_password

def image_store():
    global _image_store
    read_config()
    return _image_store
