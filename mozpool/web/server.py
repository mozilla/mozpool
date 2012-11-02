#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import templeton.handlers
import templeton.middleware
import web
import mozpool
from mozpool.lifeguard import handlers as lifeguard_handlers

templeton.middleware.patch_middleware()

def get_app():
    web.config.debug = False
    urls = templeton.handlers.load_urls(lifeguard_handlers.urls)
    return web.application(urls, lifeguard_handlers.__dict__)

def main():
    # templeton uses $PWD/../html to serve /, so put PWD in a subdirectory of
    # the directory containing our html data.  Easiest is to just change the the
    # html directory itself
    os.chdir(os.path.join(os.path.dirname(mozpool.__file__), 'html'))
    app = get_app()
    app.run()

if __name__ == '__main__':
    main()
