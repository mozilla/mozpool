# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import sys
import argparse
from mozpool.db import data
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
        if relay.powercycle(hostname, bnk, rly, timeout=60):
            print "OK"
        else:
            print "FAILED"
            sys.exit(1)
    elif cmd == 'status':
        status = relay.get_status(hostname, bnk, rly, timeout=60)
        if status is None:
            print "FAILED"
            sys.exit(1)
        print "bank %d, relay %d status: %s" % (bnk, rly, 'on' if status else 'off')
    elif cmd == 'turnon' or cmd == 'turnoff':
        status = (cmd == 'turnon')
        if relay.set_status(hostname, bnk, rly, status, timeout=60):
            print "OK"
        else:
            print "FAILED"
            sys.exit(1)
    else:
        usage()
    sys.exit(0)

epilog = """\
Add, modify, show, or list PXE configs from the Mozpool database.

With add, specify all --description and --config; --active is the default.

With show, specify only the config name.

With modify, specify any of --description, --config, and --active/--inactive.

With list, optionally specify --active to only display active configs.
"""

def pxe_config_script(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Edit BMM PXE configurations', epilog=epilog)

    parser.add_argument('--active', action='store_true', dest='active', default=None, help='PXE config is active')
    parser.add_argument('--inactive', action='store_false', dest='active', help='PXE config is not active')
    parser.add_argument('--description', '-m', help='description of the PXE config')
    parser.add_argument('--config', '-c', help='file containing configuration data; - for stdin')
    parser.add_argument('action', nargs=1, help='action to perform: add, list, show, modify')
    parser.add_argument('name', nargs='?', help='name of the PXE config')

    args = parser.parse_args(args)

    args.action = args.action[0]
    if args.action != 'list' and not args.name:
        parser.error("name is required")
    elif args.action == 'list' and args.name:
        parser.error("name is not allowed with 'list'")

    def get_config():
        if not args.config:
            parser.error('--config is required')
        if args.config == '-':
            if os.isatty(0):
                print "Enter config contents:"
            return sys.stdin.read()
        else:
            return open(args.config).read()

    def show_details(name):
        deets = data.pxe_config_details(name)['details']
        print "** Name:", deets['name'], '(inactive)' if not deets['active'] else ''
        print "** Description:", deets['description']
        print "** Contents:"
        print deets['contents'].strip()

    if args.action == 'add':
        if args.active is None:
            args.active = True
        if not args.description:
            parser.error('--description is required for --add')
        config = get_config()
        data.add_pxe_config(args.name, args.description, args.active, config)
        show_details(args.name)

    elif args.action == 'modify':
        config = None if args.config is None else get_config()
        data.update_pxe_config(args.name, args.description, args.active, config)
        show_details(args.name)

    elif args.action == 'show':
        if args.active or args.config or args.description:
            parser.error('show does not take any additional options')
        show_details(args.name)

    elif args.action == 'list':
        active_arg = {'active_only':True} if args.active else {}
        for name in data.list_pxe_configs(**active_arg)['pxe_configs']:
            show_details(name)
