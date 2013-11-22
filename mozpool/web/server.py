#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.

import os
import logging
import sys
import templeton.handlers
import templeton.middleware
import web
import mozpool.lifeguard
import mozpool.mozpool
from mozpool.web import handlers as web_handlers
from mozpool.lifeguard import devicemachine, handlers as lifeguard_handlers
from mozpool.bmm import handlers as bmm_handlers
from mozpool.mozpool import requestmachine, handlers as mozpool_handlers
from mozpool import config
from mozpool.db import setup as db_setup

templeton.middleware.patch_middleware()

def get_app(db):
    # set some global config
    web.config.debug = False
    web_handlers.Handler.db = db

    # merge handlers and URLs from all layers
    urls = ()
    handlers = dict()
    for mod in lifeguard_handlers, bmm_handlers, mozpool_handlers:
        urls = urls + mod.urls
        handlers.update(mod.__dict__)

    loaded_urls = templeton.handlers.load_urls(urls)
    return web.application(loaded_urls, handlers)

def main(run=True):
    # templeton uses $PWD/../html to serve /, so put PWD in a subdirectory of
    # the directory containing our html data.  Easiest is to just change the the
    # html directory itself
    os.chdir(os.path.join(os.path.dirname(mozpool.__file__), 'html'))

    # Set up logging
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
            format="%(name)s %(levelname)s - [%(asctime)s] %(message)s")

    # ignore urllib3 informational logging
    urllib3_logger = logging.getLogger('requests.packages.urllib3')
    urllib3_logger.setLevel(logging.CRITICAL)

    logger = logging.getLogger('')
    logger.info('Mozpool-%s server starting' % mozpool.version)

    # set up the DB layer's facade
    db = db_setup()

    # if we're running fake boards, start those up
    if config.get('testing', 'run_fakes'):
        from mozpool.test import fakedevices
        rack = fakedevices.Rack(db)
        rack.start()

    # start up the lifeguard driver
    # TODO: make this configurable, as well as poll freq
    mozpool.lifeguard.driver = devicemachine.LifeguardDriver(db)
    mozpool.lifeguard.driver.start()

    # start up the mozpool driver
    mozpool.mozpool.driver = requestmachine.MozpoolDriver(db)
    mozpool.mozpool.driver.start()

    app = get_app(db)
    if run:
        app.run()

if __name__ == '__main__':
    main()
