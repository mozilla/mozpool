# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import socket
import ConfigParser

__all__ = [
    'reset',
    'get',
    'set',
    ]

_config = None
def _load():
    global _config
    if not _config:
        defaults = {'fqdn': socket.getfqdn()}
        _config = ConfigParser.ConfigParser(defaults=defaults)
        path = os.path.join(os.path.dirname(__file__), "config.ini")
        _config.read(path)
    return _config

def reset():
    "Install an empty, blank config"
    global _config
    _config = ConfigParser.ConfigParser()

def get(*args, **kwargs):
    return _load().get(*args, **kwargs)

def set(section, key, value):
    "like ConfigParser.set, but creates sections"
    _load()
    if not _config.has_section(section):
        _config.add_section(section)
    _config.set(section, key, value)

def image_store():
    return get('paths', 'image_store')
