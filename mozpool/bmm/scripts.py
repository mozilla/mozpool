# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import with_statement
import sys
from mozpool.bmm import relay

def relay_script():
    # Basic commandline interface for testing the relay module.
    def usage():
        print "Usage: %s [powercycle|status|turnon|turnoff] <hostname> <bank> <relay>" % sys.argv[0]
        sys.exit(1)
    if len(sys.argv) != 5:
        usage()
    cmd, hostname, bnk, rly = sys.argv[1:5]
    bnk, rly = int(bnk), int(rly)
    if cmd == 'powercycle':
        if relay.powercycle(hostname, bnk, rly):
            print "OK"
        else:
            print "FAILED"
    elif cmd == 'status':
        # TODO: this shouldn't require a socket
        with relay.connected_socket(hostname, relay.PORT) as sock:
            print "bank %d, relay %d status: %d" % (bnk, rly, relay.get_status(sock, bnk, rly))
    elif cmd == 'turnon' or cmd == 'turnoff':
        # TODO: this shouldn't require a socket
        with relay.connected_socket(hostname, relay.PORT) as sock:
            status = cmd == 'turnon'
            if status == relay.set_status(sock, bnk, rly, status):
                print "OK"
            else:
                print "FAILED"
    else:
        usage()
    sys.exit(0)
