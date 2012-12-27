#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import logging
import time
import threading
import socket
import errno

PORT = 2101
COMMAND_OK = chr(85)

class Relay(object):

    def __init__(self, initial_status=0):
        self.status = initial_status

    def read_status(self):
        self.logger.debug('get status')
        return self.status

    def set_status(self, status):
        self.status = status
        device = 'off' if status else 'on'
        self.logger.info('set status %s (device %s)' % (status, device))
        self.status_changed(status, device == 'on')

    def status_changed(self, new_status, device):
        # subclasses can override this
        pass


class RelayBoard(object):

    # set this on an instance to control the time between reading a command and
    # responding to it
    delay = 0

    def __init__(self, name, addr, record_actions=False):
        """
        Create a new relay board with the given name and socket-style address.
        The relay_factory parameter will be called with (bank, relay) for each
        relay on the board, and should return a Relay instance.  It defaults to
        the Relay class.

        If record_actions is true, then relayboard.actions will contain a list
        of the actions that occurred on the board.
        """
        self.name = name
        self.addr = addr

        if record_actions:
            self.actions = []
        else:
            self.actions = None

        self.relays = {}
        self.logger = logging.getLogger('relayboard.%s' % name)
        self.stop_requested = False
        self.started_cond = threading.Condition()

    def add_relay(self, bank, relay, relay_obj):
        self.relays[(bank,relay)] = relay_obj
        relay_obj.logger = logging.getLogger('relayboard.%s.bank%d.relay%d' % (self.name, bank, relay))

    def get_port(self):
        return self.addr[1]

    def stop(self):
        self.stop_requested = True

    def spawn_one(self):
        thd = threading.Thread(target=lambda : self.run(once=True))
        thd.setDaemon(1)
        self.started_cond.acquire()
        thd.start()
        # wait until it's actually bound to the port..
        self.started_cond.wait()
        self.started_cond.release()

    def run(self, once=False):
        while not self.stop_requested:
            # listen on our designated address
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(self.addr)
            sock.listen(5)

            # If we need a dynamic port, get it now.
            if self.addr[1] == 0:
                self.addr = sock.getsockname()

            # signal the main thread that we're bound, if necessary
            self.started_cond.acquire()
            self.started_cond.notify()
            self.started_cond.release()

            # accept a single incoming connection
            csock, remote = sock.accept()

            # stop listening until we loop around again; this emulates the real boards
            sock.close()

            self.handle_commands(csock)
            csock.close()

            # bail out now if we're only running the loop once
            if once:
                return

            # emulate some extra time for the TCP stack to recover
            time.sleep(1)

    def handle_commands(self, sock):
        data = ''
        while True:
            try:
                b = sock.recv(3)
            except socket.error, e:
                if e.errno == errno.ECONNRESET:
                    return # ignore connection reset
                raise
            if self.delay:
                time.sleep(self.delay)
            if not len(b):
                return
            data = data + b
            if len(data) < 3:
                continue
            _, cmd, bank = data[:3]
            data = data[3:]
            cmd = ord(cmd)
            bank = ord(bank)
            if cmd >= 116 and cmd <= 123:
                # read status
                relay = cmd - 115
                relay_obj = self.relays.get((bank, relay))
                if not relay_obj:
                    self.logger.warning('bad bank/relay %d/%d' % (bank, relay))
                    return
                self._record_action(('get', bank, relay))
                status = relay_obj.read_status()
                sock.sendall(chr(status))
            elif cmd >= 108 and cmd <= 115:
                # turn on (panda off)
                relay = cmd - 107
                relay_obj = self.relays.get((bank, relay))
                if not relay_obj:
                    self.logger.warning('bad bank/relay %d/%d' % (bank, relay))
                    return
                self._record_action(('set', 'panda-off', bank, relay))
                relay_obj.set_status(1)
                sock.sendall(COMMAND_OK)
            elif cmd >= 100 and cmd <= 107:
                # turn off (panda on)
                relay = cmd - 99
                relay_obj = self.relays.get((bank, relay))
                if not relay_obj:
                    self.logger.warning('bad bank/relay %d/%d' % (bank, relay))
                    return
                self._record_action(('set', 'panda-on', bank, relay))
                relay_obj.set_status(0)
                sock.sendall(COMMAND_OK)
            else:
                self.logger.warning("Unknown command %d" % cmd)
                return

    def _record_action(self, action):
        if self.actions is not None:
            self.actions.append(action)

def main():
    logging.basicConfig(level=logging.DEBUG)
    relayboard = RelayBoard('fake', ('', PORT), Relay)
    for bank in 1, 2:
        for relay in 1, 2, 3, 4, 5, 6, 7, 8:
            relayboard.add_relay(bank, relay, Relay())
    relayboard.run()

if __name__ == '__main__':
    main()
