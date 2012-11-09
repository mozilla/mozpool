#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import time
import threading
import socket, sys, SocketServer

PORT = 2101
COMMAND_OK = chr(85)

# 4 banks of 8 relays
relays = [[0]*8 for i in range(5)]
class RelayTCPHandler(SocketServer.BaseRequestHandler):
    def handle(self):
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
                print "Invalid bank %d" % bank
                return
            if cmd >= 116 and cmd <= 123:
                # read status
                relay = cmd - 115
                print "get status bank %d relay %d" % (bank, relay)
                self.server.actions.append(('get', bank, relay))
                self.request.sendall(chr(relays[bank - 1][relay - 1]))
            elif cmd >= 108 and cmd <= 115:
                # turn on
                relay = cmd - 107
                print "turn on bank %d relay %d (panda off)" % (bank, relay)
                relays[bank - 1][relay - 1] = 1
                self.server.actions.append(('set', 'panda-off', bank, relay))
                self.request.sendall(COMMAND_OK)
            elif cmd >= 100 and cmd <= 107:
                # turn off
                relay = cmd - 99
                print "turn off bank %d relay %d (panda on)" % (bank, relay)
                relays[bank - 1][relay - 1] = 0
                self.server.actions.append(('set', 'panda-on', bank, relay))
                self.request.sendall(COMMAND_OK)
            else:
                print "Unknown command %d" % cmd

class RelayTCPServer(SocketServer.TCPServer):
    allow_reuse_address = True

    def __init__(self, addr):
        SocketServer.TCPServer.__init__(self, addr, RelayTCPHandler)
        self.actions = []
        self.delay = 0

    def get_port(self):
        return self.socket.getsockname()[1]

    def spawn_one(self):
        self.thd = threading.Thread(target=self.handle_request)
        self.thd.setDaemon(1)
        self.thd.start()

def main():
    server = RelayTCPServer(('', PORT))
    server.serve_forever()

if __name__ == '__main__':
    main()
