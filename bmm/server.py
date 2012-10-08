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

def main():
    # load test data
    # TODO: this should probably come from the config
    if len(sys.argv) > 1:
        # load the data from argv[1]
        globals = {}
        execfile(sys.argv[1], globals)
        data.servers = globals['data']
        del sys.argv[0]

    urls = templeton.handlers.load_urls(handlers.urls)
    app = web.application(urls, handlers.__dict__)
    app.run()

if __name__ == '__main__':
    main()
