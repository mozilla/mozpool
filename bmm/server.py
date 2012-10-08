#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import templeton.handlers
import templeton.middleware
import web
from bmm import handlers, data

templeton.middleware.patch_middleware()

def get_app():
    urls = templeton.handlers.load_urls(handlers.urls)
    return web.application(urls, handlers.__dict__)

def main():
    # load test data
    if len(sys.argv) > 1:
        # load the data from argv[1]
        execfile(sys.argv[1])
        del sys.argv[1]

    app = get_app()
    app.run()

if __name__ == '__main__':
    main()
