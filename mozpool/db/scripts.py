# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
from mozpool.db import setup
from mozpool.db import model

def db_script():
    # Basic commandline interface for testing the relay module.
    def usage():
        print "Usage: %s create-schema -- create the DB schema in the configured DB" % sys.argv[0]
        print "Usage: %s run mydata.py -- run mydata.py with an open connection `conn`" % sys.argv[0]
        sys.exit(1)
    if len(sys.argv) < 2:
        usage()
    if sys.argv[1] == 'create-schema':
        db = setup()
        model.metadata.create_all(bind=db.pool.engine)
    elif sys.argv[1] == 'run':
        db = setup()
        execfile(sys.argv[2], dict(conn=db.pool.engine.connect(), args=sys.argv[3:]))
    else:
        usage()
    sys.exit(0)
