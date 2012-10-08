#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# just a server with some crummy mocked-up data for initial testing

from bmm import server
from bmm import data

data.servers = {'eye7': {'board1': {'server':'eye7',
                                    'state':'offline',
                                    'log': [],
                                    'config': {'foo': 1},
                                    'relay-info': 'relay-1:bank1:relay1',
                                    }
                         }
                }
server.app.run()
