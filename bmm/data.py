# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import socket

# Hard-coded data for now
servers = {}

bootimages = {}

class NotFound(Exception):
    pass

def list_boards_for_imaging_server(server):
    #TODO: database query
    if server not in servers:
        raise NotFound
    return {'boards': servers[server].keys()}

def get_server_for_board(board):
    #TODO: database query
    for server, boards in servers.iteritems():
        if board in boards:
            return server
    raise NotFound

# The rest of the board methods should not have to check for a valid board.
# Handler methods will check before calling.
def board_status(board):
    #TODO: database query
    server = socket.getfqdn()
    return {'state': servers[server][board]['state'],
            'log': servers[server][board]['log']}

def set_board_status(board, state):
    #TODO: database update
    servers[socket.getfqdn()][board]['state'] = state
    return servers[socket.getfqdn()][board]['state']

def board_config(board):
    #TODO: database query
    return {'config': servers[socket.getfqdn()][board]['config']}

def set_board_config(board, config):
    #TODO: database update
    servers[socket.getfqdn()][board]['config'] = config

def board_relay_info(board):
    #TODO: database query
    info = servers[socket.getfqdn()][board]['relay-info']
    hostname, bank, relay = info.split(":", 2)
    assert bank.startswith("bank") and relay.startswith("relay")
    return hostname, int(bank[4:]), int(relay[5:])

def add_log(board, message):
    #TODO: database insert
    servers[socket.getfqdn()][board]['log'].append(message)

def list_bootimages():
    #TODO: database query
    return {'bootimages': bootimages.keys()}

def bootimage_details(image):
    #TODO: database query
    if image not in bootimages:
        raise NotFound
    return {'details': bootimages[image]}
