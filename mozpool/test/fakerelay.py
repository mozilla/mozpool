#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import logging
import time
import threading
import socket, sys, SocketServer

PORT = 2101
COMMAND_OK = chr(85)

logger = logging.getLogger('fakerelay')

# 4 banks of 8 relays
relays = [[0]*8 for i in range(5)]
class RelayTCPHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        if self.server.close_on_connect:
            self.server.server_close()
        data = []
        while True:
            b = self.request.recv(3)
            if not len(b):
                return
            data.extend(b)
            if len(data) < 3:
                continue
            _, cmd, bank = data[:3]
            data = data[3:]
            cmd = ord(cmd)
            bank = ord(bank)
            if self.server.delay:
                time.sleep(self.server.delay)
            if bank < 1 or bank > 4:
                logging.info("Invalid bank %d" % bank)
                return
            if cmd >= 116 and cmd <= 123:
                # read status
                relay = cmd - 115
                logging.info("get status bank %d relay %d" % (bank, relay))
                self.server.actions.append(('get', bank, relay))
                self.request.sendall(chr(relays[bank - 1][relay - 1]))
            elif cmd >= 108 and cmd <= 115:
                # turn on
                relay = cmd - 107
                logging.info("turn on bank %d relay %d (panda off)" % (bank, relay))
                relays[bank - 1][relay - 1] = 1
                self.server.actions.append(('set', 'panda-off', bank, relay))
                self.request.sendall(COMMAND_OK)
            elif cmd >= 100 and cmd <= 107:
                # turn off
                relay = cmd - 99
                logging.info("turn off bank %d relay %d (panda on)" % (bank, relay))
                relays[bank - 1][relay - 1] = 0
                self.server.actions.append(('set', 'panda-on', bank, relay))
                self.request.sendall(COMMAND_OK)
            else:
                logging.info("Unknown command %d" % cmd)

class RelayTCPServer(SocketServer.TCPServer):
    allow_reuse_address = True

    def __init__(self, addr):
        SocketServer.TCPServer.__init__(self, addr, RelayTCPHandler)
        self.actions = []
        # how long to delay between getting a command and executing it
        self.delay = 0
        # if true, shut down the listening socket as soon as a connection comes in,
        # emulating real relays a bit better
        self.close_on_connect = False

    def get_port(self):
        return self.socket.getsockname()[1]

    def spawn_one(self):
        self.thd = threading.Thread(target=self.handle_request)
        self.thd.setDaemon(1)
        self.thd.start()

def main():
    logging.basicConfig(level=logging.DEBUG)
    while True:
        server = RelayTCPServer(('', PORT))
        server.close_on_connect = True
        server.handle_request()
        logging.info("relay board resetting..")
        time.sleep(1)

if __name__ == '__main__':
    main()
