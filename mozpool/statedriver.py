# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import abc
import time
import threading
import logging

####
# Driver

POLL_FREQUENCY = 10

class StateDriver(threading.Thread):
    """
    A generic state-machine driver.  This handles timeouts, as well as handling
    any events triggered externally.
    """
    __metaclass__ = abc.ABCMeta

    # override all these
    state_machine_cls = None
    logger_name = 'state'
    thread_name = 'StateDriver'
    log_db_handler = None

    def __init__(self, poll_frequency=POLL_FREQUENCY):
        threading.Thread.__init__(self, name=self.thread_name)
        self.setDaemon(True)
        self._stop = False
        self.poll_frequency = poll_frequency
        self.logger = logging.getLogger(self.logger_name)
        self.log_handler = self.log_db_handler()
        self.logger.addHandler(self.log_handler)

    def stop(self):
        self._stop = True
        self.join()
        self.logger.removeHandler(self.log_handler)

    def run(self):
        try:
            # a tight loop that just launches the polling in a thread.  Then, if
            # it takes more than the poll interval, we can log loudly, but there's
            # nothing in this loop that's at risk of breaking
            while True:
                if self._stop:
                    self.logger.info("stopping on request")
                    break

                started_at = time.time()
                polling_thd = threading.Thread(target=self._tick)
                polling_thd.setDaemon(1)
                polling_thd.start()

                time.sleep(self.poll_frequency)
                # if the thread is still alive, we have a problem
                delay = 1
                while polling_thd.isAlive():
                    elapsed = time.time() - started_at
                    self.logger.warning("polling thread still running at %ds; not starting another" % elapsed)
                    time.sleep(delay)
                    # exponential backoff up to 1m
                    delay = delay if delay > 60 else delay * 1.1
        except Exception:
            self.logger.error("run loop failed", exc_info=True)
        finally:
            self.logger.warning("run loop returned (this should not happen!)")

    def _tick(self):
        try:
            self.poll_for_timeouts()
            self.poll_others()
        except Exception:
            self.logger.error("failure in _tick", exc_info=True)
            # don't worry, we'll get called again, for surez..

    def handle_event(self, machine_name, event, args):
        """
        Handle an event for a particular device, with optional arguments
        specific to the event.
        """
        machine = self._get_machine(machine_name)
        machine.handle_event(event, args)

    def conditional_state_change(self, machine_name, old_state, new_state):
        """
        Transition to NEW_STATE only if the device is in OLD_STATE.
        Returns True on success, False on failure.
        """
        machine = self._get_machine(machine_name)
        return machine.conditional_goto_state(old_state, new_state)

    def poll_for_timeouts(self):
        for machine_name in self._get_timed_out_machine_names():
            self.logger.info("handling timeout on %s" % machine_name)
            machine = self._get_machine(machine_name)
            try:
                machine.handle_timeout()
            except:
                self.logger.error("(ignored) error while handling timeout:",
                                exc_info=True)

    def _get_machine(self, machine_name):
        return self.state_machine_cls(machine_name)
    
    def poll_others(self):
        """
        Override with any activities to be performed each pass through the
        loop.
        """
        pass

    @abc.abstractmethod
    def _get_timed_out_machine_names(self):
        return []


####
# Logging handler

class DBHandler(logging.Handler):

    object_name = ''
    log_object = None

    def emit(self, record):
        logger = record.name.split('.')
        if len(logger) != 2 or logger[0] != self.object_name:
            return
        name = logger[1]

        msg = self.format(record)
        self.log_object.add(name, msg, source='statemachine')
