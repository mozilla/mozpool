# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton
from mozpool.db import data

# URLs go here. "/api/" will be automatically prepended to each.
urls = (
  "/bmm/pxe_config/list/?", "pxe_config_list",
  "/bmm/pxe_config/([^/]+)/details/?", "pxe_config_details",
)

class pxe_config_list:
    @templeton.handlers.json_response
    def GET(self):
        return data.list_pxe_configs()

class pxe_config_details:
    @templeton.handlers.json_response
    def GET(self, id):
        return data.pxe_config_details(id)

