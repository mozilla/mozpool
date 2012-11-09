# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os

# unfortunately, sending ICMP packets requires a raw socket, which requires
# being root.  Instead, we use 'fping', which is nice and scriptable.

def ping(fqdn):
    # ping quietly, try four times, waiting 50ms for a response
    status = os.system("fping -q -r4 -t50 %s" % fqdn)
    if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0:
        return True
    return False
