#!/usr/bin/python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/
#
# The original repository for this code is:
# http://hg.mozilla.org/users/tmielczarek_mozilla.com/relay-control

"""
This module provides methods to control relays on a National Control Devices
ProXR networkable relay board. Each board can have up to 4 banks of relays,
with each bank containing up to 8 relays. All methods in this module
require the bank number and the relay number within that bank to be specified,
with numbering starting at 1.

This module assumes that devices are wired to the Normal Closed (N.C.) side
of the relays, so that when a relay is OFF the device is receiving power,
and when a relay is ON the device is not receiving power.

All three externally available methods here take a timeout argument, and go to
great lengths to ensure that the function execution will not take longer than
that, regardless of network conditions.
"""

from __future__ import with_statement
import sys
import time
import socket
import asyncore
import logging
from mozpool import util
from contextlib import contextmanager

__all__ = ['get_status',
           'set_status',
           'powercycle']

DEFAULT_PORT = 2101

locks = util.LocksByName()
logger = logging.getLogger('bmm.relay')

# Some magic numbers from the manual
# Command completed successfully
COMMAND_OK = chr(85)

# Enter command mode.
START_COMMAND = chr(254)

def READ_RELAY_N_AT_BANK(N):
    """
    Return command code for reading status of relay N in a bank.
    """
    return chr(115 + N)

def TURN_ON_RELAY_N_AT_BANK(N):
    """
    Return command code for turning on relay N in a bank.
    """
    return chr(107 + N)

def TURN_OFF_RELAY_N_AT_BANK(N):
    """
    Return command code for turning off relay N in a bank.
    """
    return chr(99 + N)

def status2cmd(status, relay):
    if status:
        return TURN_OFF_RELAY_N_AT_BANK(relay)
    else:
        return TURN_ON_RELAY_N_AT_BANK(relay)

def res2status(res):
    return False if ord(res[0]) == 1 else True

@contextmanager
def serialize_by_host(hostname):
    """
    Ensure that exactly one enclosed block with the given hostname can run at a
    time on this host.  This accounts for a small wait time *after* the connection
    to allow the relay board to reset (its TCP stack appears to be single-threaded!)
    """
    locks.acquire(hostname)
    try:
        yield
    finally:
        # sleep long enough for the relay board to recover after the TCP connection
        time.sleep(1)
        locks.release(hostname)

class TimeoutError(Exception):
    pass

class ConnectionLostError(Exception):
    pass

class RelayClient(asyncore.dispatcher):
    """
    A client for the relay protocol.  The transaction is driven by a coroutine.
    The coroutine must complete within TIMEOUT seconds, and does not begin until
    the socket is connected.  The coroutine takes a single argument, the client,
    and can yield to read or write::

        yield client.write(data)
        data = yield client.read()

    And the socket is closed when the coroutine ends.

    This is generally used in a thread for a single socket.  The advantage is
    that it allows a timeout to be applied even to connect operations.
    """

    @classmethod
    def generator(cls, host, timeout):
        # try to split host into host:port, applying the default
        if ':' in host:
            host, port = host.split(':')
            port = int(port)
        else:
            port = DEFAULT_PORT
        def wrap(generator):
            def run():
                client = cls(host, port, timeout, generator)
                return client.run()
            return run
        return wrap

    def __init__(self, host, port, timeout, generator):
        # use a unique map here to avoid asyncore keeping a reference to this object
        # around forever if close() isn't called correctly
        asyncore.dispatcher.__init__(self, map={})
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host = host
        self.port = port
        self.connect( (host, port) )
        self.state = 'connecting'
        self.output = ''
        self.complete_by = time.time() + timeout
        self.coroutine = generator(self)

    def read(self):
        if self.state != 'idle':
            return
        self.state = 'reading'
        return self

    def write(self, data):
        if self.state != 'idle':
            return
        self.state = 'writing'
        self.output += data
        return self

    def handle_connect(self):
        if self.state != 'connecting':
            return
        self.state = 'idle'
        self._step()

    def handle_close(self):
        self._step(exc=(ConnectionLostError(),))

    def handle_timeout(self):
        self._step(exc=(TimeoutError(),))

    def handle_error(self):
        self._step(exc=sys.exc_info())

    def handle_read(self):
        if self.state != 'reading':
            return
        self.state = 'idle'
        self._step(self.recv(8192))

    def handle_write(self):
        if self.state != 'writing':
            # handle_write is sometimes called after a connection succeeds
            return
        sent = self.send(self.output)
        self.output = self.output[sent:]
        if not self.output:
            self.state = 'idle'
            self._step()

    def writable(self):
        return self.state == 'writing' or self.state == 'connecting'

    def readable(self):
        return self.state == 'reading'

    def run(self):
        try:
            while self.state != 'done':
                timeout = self.complete_by - time.time()
                if timeout <= 0:
                    if self.state != 'done':
                        self.handle_timeout()
                    return

                asyncore.loop(timeout=timeout, count=1, map={self.fileno() : self})
        finally:
            # be sure to call close unconditionally
            self.close()
        return self.return_value

    def _step(self, value=None, exc=None):
        if exc:
            to_call = self.coroutine.throw, exc
        else:
            to_call = self.coroutine.send, (value,)

        try:
            to_call[0](*to_call[1])
            assert self.state != 'idle', "coroutine yielded without anything to do"
        except StopIteration, e:
            self.close()
            self.state = 'done'
            if e.args:
                self.return_value = e.args[0]
            else:
                self.return_value = None

## external API (but internal to BMM)

def get_status(host, bank, relay, timeout):
    """
    Get the status of a relay on a specified bank on the given host, within
    TIMEOUT seconds.  Returns None on error, and otherwise a boolean (True
    meaning "on").
    """
    assert(bank >= 1 and bank <= 4)
    assert(relay >= 1 and relay <= 8)
    @RelayClient.generator(host, timeout)
    def gen(client):
        yield client.write(START_COMMAND)
        yield client.write(READ_RELAY_N_AT_BANK(relay))
        yield client.write(chr(bank))
        # relay board will return 0 or 1 indicating its state
        res = yield client.read()
        raise StopIteration(res2status(res))
    return _run_gen(host, gen, on_error=None)

def set_status(host, bank, relay, status, timeout):
    """

    Set the status of a relay on a specified bank on the given host, within
    TIMEOUT seconds.

    If status is True, turn on the specified device. If it is False,
    turn off the specified relay.

    Return True on success, or False on error.
    """
    assert(bank >= 1 and bank <= 4)
    assert(relay >= 1 and relay <= 8)

    @RelayClient.generator(host, timeout)
    def gen(client):
        logger.info("set_status(%s) on %s bank %s relay %s initiated" % (status, host, bank, relay))
        yield client.write(START_COMMAND)
        yield client.write(status2cmd(status, relay))
        yield client.write(chr(bank))
        res = yield client.read()
        if res != COMMAND_OK:
            logger.error("Command on %s did not succeed, status: %d" % (host, ord(res)))
            raise StopIteration(False)
        else:
            raise StopIteration(True)
    return _run_gen(host, gen)

def powercycle(host, bank, relay, timeout):
    """
    Cycle the power of a device connected to a relay on a specified bank
    on the board at the given hostname.

    The relay will be turned on and then off, with status checked
    after each operation.

    Return True if successful, False otherwise.
    """
    assert(bank >= 1 and bank <= 4)
    assert(relay >= 1 and relay <= 8)

    @RelayClient.generator(host, timeout)
    def gen(client):
        logger.info("power-cycle on %s bank %s relay %s initiated" % (host, bank, relay))
        # sadly, because we don't have 'yield from' yet, this all has to happen
        # in one function body.
        for status in False, True:
            # set the status
            yield client.write(START_COMMAND)
            yield client.write(status2cmd(status, relay))
            yield client.write(chr(bank))
            res = yield client.read()
            if res != COMMAND_OK:
                logger.info("Command on %s did not succeed, status: %d" % (host, ord(res)))
                raise StopIteration(False)

            # check the status
            yield client.write(START_COMMAND)
            yield client.write(READ_RELAY_N_AT_BANK(relay))
            yield client.write(chr(bank))
            res = yield client.read()
            got_status = res2status(res)
            if (not status and got_status) or (status and not got_status):
                logger.info("Bank %d relay %d on %s did not change state" % (bank, relay, host))
                raise StopIteration(False)

            # if we just turned the device off, give it a chance to rest
            if status is False:
                time.sleep(1)
        logger.info("power-cycle on %s bank %s relay %s successful" % (host, bank, relay))
        raise StopIteration(True)
    return _run_gen(host, gen)

def _run_gen(host, gen, on_error=False):
    try:
        with serialize_by_host(host):
            return gen()
    except TimeoutError:
        logger.error("timeout communicating with %s" % (host,))
        return on_error
    except ConnectionLostError:
        logger.error("connection to %s lost" % (host,))
        return on_error
    except socket.error, e:
        # handle the common case with less traceback
        if e.errno == 111:
            logger.error("error communicating with relay host %s: connection refused" % (host,))
        else:
            logger.error("error communicating with relay host %s" % (host,), exc_info=e)
        return on_error
