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
import time
import socket
import logging
import errno
from mozpool import util
from contextlib import contextmanager

__all__ = ['get_status',
           'set_status',
           'powercycle']

DEFAULT_PORT = 2101

# this is set to something shorter for the tests
ONE_SECOND = 1

locks = util.LocksByName()
logger = logging.getLogger('bmm.relay')

# Some magic numbers from the manual
# Command completed successfully
COMMAND_OK = chr(85)

# Enter command mode.
START_COMMAND = chr(254)

# Two-way comms check command
TEST_2_WAY_COMMS = chr(33)

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
def serialize_by_relay_board(relay_board_name):
    """
    Ensure that exactly one enclosed block with the given relay_board_name can run at a
    time on this host.  This accounts for a small wait time *after* the connection
    to allow the relay board to reset (its TCP stack appears to be single-threaded!)
    """
    locks.acquire(relay_board_name)
    try:
        yield
    finally:
        # sleep long enough for the relay board to recover after the TCP connection
        time.sleep(ONE_SECOND)
        locks.release(relay_board_name)

class TimeoutError(Exception):
    pass

def set_timeout(sock, before):
    remaining = before - time.time()
    if remaining <= 0:
        raise TimeoutError
    sock.settimeout(remaining)

@contextmanager
def connected_socket(relay_board_name, before):
    with serialize_by_relay_board(relay_board_name):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        set_timeout(sock, before)
        if ':' in relay_board_name:
            host, port = relay_board_name.split(':')
            port = int(port)
        else:
            host = relay_board_name
            port = DEFAULT_PORT
        sock.connect((host, port))
        yield sock
        sock.close()

def timed_read(sock, before):
    set_timeout(sock, before)
    return sock.recv(1024)

def timed_write(sock, data, before):
    set_timeout(sock, before)
    return sock.sendall(data)

def log_errors(on_error):
    def wrap(fn):
        def replacement(relay_board_name, *args, **kwargs):
            try:
                return fn(relay_board_name, *args, **kwargs)
            except (TimeoutError, socket.timeout):
                logger.error("timeout communicating with %s" % (relay_board_name,))
                return on_error
            except socket.error, e:
                # handle the common case with less traceback
                if e.errno == errno.ECONNREFUSED:
                    logger.error("error communicating with relay board %s: connection refused" % (relay_board_name,))
                else:
                    logger.error("error communicating with relay board %s" % (relay_board_name,), exc_info=e)
                return on_error
        return replacement
    return wrap

## external API (but internal to BMM)

@log_errors(on_error=False)
def test_two_way_comms(relay_board_name, timeout):
    """
    Test the two way communications between the ProXR microcontroller and the Digi Connect network module.
    This simply sends a NOOP command to the controler which expects an OK(85) reply.  False on errors.
    """
    before = time.time() + timeout
    with connected_socket(relay_board_name, before) as sock:
        timed_write(sock, START_COMMAND + TEST_2_WAY_COMMS, before)
        res = timed_read(sock, before)
        return res2status(res)

@log_errors(on_error=None)
def get_status(relay_board_name, bank, relay, timeout):
    """
    Get the status of a relay on a specified bank on the given relay board,
    within TIMEOUT seconds.  Returns None on error, and otherwise a boolean
    (True meaning "on").
    """
    before = time.time() + timeout

    assert(bank >= 1 and bank <= 4)
    assert(relay >= 1 and relay <= 8)

    with connected_socket(relay_board_name, before) as sock:
        timed_write(sock, START_COMMAND + READ_RELAY_N_AT_BANK(relay) + chr(bank), before)
        res = timed_read(sock, before)
        return res2status(res)

@log_errors(on_error=False)
def set_status(relay_board_name, bank, relay, status, timeout):
    """
    Set the status of a relay on a specified bank on the given relay board, within
    TIMEOUT seconds.

    If status is True, turn on the specified device. If it is False,
    turn off the specified relay.

    Return True on success, or False on error.
    """
    before = time.time() + timeout
    assert(bank >= 1 and bank <= 4)
    assert(relay >= 1 and relay <= 8)

    with connected_socket(relay_board_name, before) as sock:
        logger.info("set_status(%s) on %s bank %s relay %s initiated" % (status, relay_board_name, bank, relay))
        timed_write(sock, START_COMMAND + status2cmd(status, relay) + chr(bank), before)
        res = timed_read(sock, before)
        if res != COMMAND_OK:
            logger.error("Command on %s did not succeed, status: %d" % (relay_board_name, ord(res)))
            return False
        else:
            return True

@log_errors(on_error=False)
def powercycle(relay_board_name, bank, relay, timeout):
    """
    Cycle the power of a device connected to a relay on a specified bank
    on the given relay board.

    The relay will be turned on and then off, with status checked
    after each operation.

    Return True if successful, False otherwise.
    """
    before = time.time() + timeout
    assert(bank >= 1 and bank <= 4)
    assert(relay >= 1 and relay <= 8)

    with connected_socket(relay_board_name, before) as sock:
        logger.info("power-cycle on %s bank %s relay %s initiated" % (relay_board_name, bank, relay))
        for status in False, True:
            # set the status
            timed_write(sock, START_COMMAND + status2cmd(status, relay) + chr(bank), before)
            res = timed_read(sock, before)
            if res != COMMAND_OK:
                logger.info("Command on %s did not succeed, status: %d" % (relay_board_name, ord(res)))
                return False

            # check the status
            timed_write(sock, START_COMMAND + READ_RELAY_N_AT_BANK(relay) + chr(bank), before)
            res = timed_read(sock, before)
            got_status = res2status(res)
            if (not status and got_status) or (status and not got_status):
                logger.info("Bank %d relay %d on %s did not change state" % (bank, relay, relay_board_name))
                return False

            # if we just turned the device off, give it a chance to rest
            if status is False:
                time.sleep(ONE_SECOND)
        logger.info("power-cycle on %s bank %s relay %s successful" % (relay_board_name, bank, relay))
        return True

