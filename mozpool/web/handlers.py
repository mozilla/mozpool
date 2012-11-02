# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Functions common to all handlers."""

import json
import web.webapi

nocontent = NoContent = web.webapi._status_code("204 No Content")
