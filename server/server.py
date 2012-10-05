#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import templeton.handlers
import templeton.middleware
import handlers
import web

templeton.middleware.patch_middleware()

urls = templeton.handlers.load_urls(handlers.urls)

app = web.application(urls, handlers.__dict__)


if __name__ == '__main__':
    app.run()
