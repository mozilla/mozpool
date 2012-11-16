# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import abc
import time
import threading
import logging
from db import logs

####
# Driver

POLL_FREQUENCY = 10

class StateDriver(threading.Thread):
    """
    A generic state-machine driver.  This handles timeouts, as well as handling
    any events triggered externally.
    """
    __metaclass__ = abc.ABCMeta

    state_machine_cls = None
    logger_name = 'state'
    thread_name = 'StateDriver'

    def __init__(self, poll_frequency=POLL_FREQUENCY):
        threading.Thread.__init__(self, name=self.thread_name)
        self.setDaemon(True)
        self._stop = False
        self.poll_frequency = poll_frequency
        self.logger = logging.getLogger(self.logger_name)
        self.log_handler = DBHandler()
        self.logger.addHandler(self.log_handler)

    def stop(self):
        self._stop = True
        self.join()
        self.logger.removeHandler(self.log_handler)

    def run(self):
        last_poll = 0
        while True:
            # wait for our poll interval
            seconds_left = last_poll + self.poll_frequency - time.time()
            if seconds_left > 0:
                time.sleep(seconds_left)
            if self._stop:
                break

            last_poll = time.time()
            for machine_name in self._get_timed_out_machine_names():
                machine = self._get_machine(machine_name)
                try:
                    machine.handle_timeout()
                except:
                    self.logger.error("(ignored) error while handling timeout:",
                                      exc_info=True)

    def handle_event(self, machine_name, event, args):
        """
        Handle an event for a particular device, with optional arguments
        specific to the event.
        """
        machine = self._get_machine(machine_name)
        machine.handle_event(event, args)

    def conditional_state_change(self, machine_name, old_state, new_state,
                                 call_first):
        """
        Transition to NEW_STATE only if the device is in OLD_STATE.
        Simultaneously set the PXE config and boot config as described, or
        clears the PXE config if new_pxe_config is None.
        Returns True on success, False on failure.
        """
        machine = self._get_machine(machine_name)
        return machine.conditional_goto_state(old_state, new_state, call_first)

    def _get_machine(self, machine_name):
        return self.state_machine_cls(machine_name)

    @abc.abstractmethod
    def _get_timed_out_machine_names(self):
        return []


####
# Logging handler

class DBHandler(logging.Handler):

    def emit(self, record):
        # get the device name
        logger = record.name.split('.')
        if len(logger) != 2 or logger[0] != 'device':
            return
        device_name = logger[1]

        msg = self.format(record)
        logs.device_logs.add(device_name, msg, source='statemachine')
