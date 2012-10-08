#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Put some fake data into a sqlite database. Useful for testing.
"""

import socket
from bmm import testing

fqdn=socket.getfqdn()
testing.create_sqlite_db("/tmp/imaging-testserver.sqlite")
testing.add_server(fqdn)
testing.add_board("board1", server=fqdn)
testing.add_bootimage("image1")
