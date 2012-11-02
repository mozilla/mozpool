#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

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
            if bank < 1 or bank > 4:
                print "Invalid bank %d" % bank
                return
            if cmd >= 116 and cmd <= 123:
                # read status
                relay = cmd - 115
                print "get status bank %d relay %d" % (bank, relay)
                self.request.sendall(chr(relays[bank - 1][relay - 1]))
            elif cmd >= 108 and cmd <= 115:
                # turn on
                relay = cmd - 107
                print "turn on bank %d relay %d" % (bank, relay)
                relays[bank - 1][relay - 1] = 1
                self.request.sendall(COMMAND_OK)
            elif cmd >= 100 and cmd <= 107:
                # turn off
                relay = cmd - 99
                print "turn off bank %d relay %d" % (bank, relay)
                relays[bank - 1][relay - 1] = 0
                self.request.sendall(COMMAND_OK)
            else:
                print "Unknown command %d" % cmd

class RelayTCPServer(SocketServer.TCPServer):
    allow_reuse_address = True

def main():
    server = RelayTCPServer(('', PORT), RelayTCPHandler)
    server.serve_forever()

if __name__ == '__main__':
    main()
