# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
import threading
import datetime
import logging
from mozpool.db import data
from mozpool import statemachine
from mozpool import config
from mozpool.bmm import api as bmm_api
import mozpool.lifeguard

####
# Driver

POLL_FREQUENCY = 10

class LifeguardDriver(threading.Thread):
    """
    A driver for lifeguard.  This handles timeouts, as well as handling any
    events triggered externally.

    The server code sets up an instance of this object as mozpool.lifeguard.driver.
    """

    # TODO: abstract and put in statemachine.py

    def __init__(self, poll_frequency=POLL_FREQUENCY):
        threading.Thread.__init__(self, name='LifeguardDriver')
        self.setDaemon(True)
        self.imaging_server_id = data.find_imaging_server_id(config.get('server', 'fqdn'))
        self._stop = False
        self.poll_frequency = poll_frequency
        self.logger = logging.getLogger('lifeguard.driver')

    def stop(self):
        self._stop = True
        self.join()

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
            for device_name in data.get_timed_out_devices(self.imaging_server_id):
                machine = self._get_machine(device_name)
                try:
                    machine.handle_timeout()
                except:
                    self.logger.error("(ignored) error while handling timeout:", exc_info=True)

    def handle_event(self, device_name, event):
        """
        Handle an event for a particular device.
        """
        machine = self._get_machine(device_name)
        machine.handle_event(event)

    def conditional_state_change(self, device_name, old_state, new_state,
                new_pxe_config, new_boot_config):
        """
        Transition to NEW_STATE only if the device is in OLD_STATE.
        Simultaneously set the PXE config and boot config as described, or
        clears the PXE config if new_pxe_config is None.
        Returns True on success, False on failure.
        """
        machine = self._get_machine(device_name)
        def call_first():
            if new_pxe_config is None:
                bmm_api.clear_pxe(device_name)
            else:
                bmm_api.set_pxe(device_name, new_pxe_config, new_boot_config)
        return machine.conditional_goto_state(old_state, new_state, call_first)

    def _get_machine(self, device_name):
        return DeviceStateMachine(device_name)

####
# State machine

class DeviceStateMachine(statemachine.StateMachine):

    def __init__(self, device_name):
        statemachine.StateMachine.__init__(self, "device-%s" % device_name)
        self.device_name = device_name

    def read_state(self):
        state, timeout, counters = data.get_device_state(self.device_name)
        return state

    def write_state(self, new_state, timeout_duration):
        if timeout_duration:
            state_timeout = datetime.datetime.now() + datetime.timedelta(seconds=timeout_duration)
        else:
            state_timeout = None
        data.set_device_state(self.device_name, new_state, state_timeout)

    def read_counters(self):
        state, timeout, counters = data.get_device_state(self.device_name)
        return counters

    def write_counters(self, counters):
        data.set_device_counters(self.device_name, counters)


####
# Mixins

class AllowReboot(object):

    @statemachine.event_method('rq-reboot')
    def on_rq_reboot(self):
        self.machine.goto_state(pc_rebooting)


####
# Initial and steady states

@DeviceStateMachine.state_class
class new(AllowReboot, statemachine.State):
    "This device is newly installed.  Await instructions."


@DeviceStateMachine.state_class
class unknown(AllowReboot, statemachine.State):
    "This device is in an unknown state.  Await instructions."


@DeviceStateMachine.state_class
class ready(AllowReboot, statemachine.State):
    "This device is production-ready."

    TIMEOUT = 300

    ## TODO: polling stuff isn't implemented yet

    def on_entry(self):
        self.machine.clear_counter()
        #start_polling()

    def on_exit(self):
        #stop_polling()
        pass

    @statemachine.timeout_method(TIMEOUT)
    def on_timeout(self):
        self.machine.goto_state(ready)

    @statemachine.event_method('poll-ok')
    def on_poll_ok(self):
        pass # wait for the timeout to expire, rather than immediately re-polling

    @statemachine.event_method('poll-failure')
    def on_poll_failure(self):
        self.machine.goto_state(pc_rebooting)


####
# Power Cycling

@DeviceStateMachine.state_class
class pc_rebooting(statemachine.State):
    "A reboot has been requested, and the device is being power-cycled."

    # wait for 60 seconds for a poer cycle to succeed, and do this a bunch of
    # times; failures here are likely a problem with the network or relay board,
    # so we want to retry until that's available.

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 200

    def on_entry(self):
        # kick off a power cycle on entry
        def powercycle_done(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'power-cycle-ok')
        bmm_api.clear_pxe(self.machine.device_name)
        bmm_api.start_powercycle(self.machine.device_name, powercycle_done)

    @statemachine.timeout_method(TIMEOUT)
    def on_timeout(self):
        if self.machine.increment_counter('pc_rebooting') > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_reboot_rebooting)
        else:
            self.machine.goto_state(pc_rebooting)

    @statemachine.event_method('power-cycle-ok')
    def on_power_cycle_ok(self):
        self.machine.clear_counter('pc_rebooting')
        self.machine.goto_state(pc_pinging)


@DeviceStateMachine.state_class
class pc_pinging(statemachine.State):
    "A reboot has been requested, and the power cycle is complete.  Ping until successful."

    # ping every 10s, failing 12 times
    TIMEOUT = 10
    PERMANENT_FAILURE_COUNT = 3

    def on_entry(self):
        def ping_complete(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'ping-ok')
        bmm_api.start_ping(self.machine.device_name, ping_complete)

    @statemachine.timeout_method(TIMEOUT)
    def on_timeout(self):
        if self.machine.increment_counter('pc_pinging') > self.PERMANENT_FAILURE_COUNT:
            # after enough ping failures, try rebooting again (and clear the ping counter)
            self.machine.clear_counter('pc_pinging')
            self.machine.goto_state(pc_rebooting)
        else:
            # otherwise, re-enter this state and ping again
            self.machine.goto_state(pc_pinging)

    # TODO: not clear how to know the image is running -- ping?
    # https://github.com/jedie/python-ping/blob/master/ping.py
    @statemachine.event_method('ping-ok')
    def on_image_running(self):
        self.machine.clear_counter('pc_pinging')
        self.machine.goto_state(ready)

####
# Failure states

class failed(AllowReboot, statemachine.State):
    "Parent class for failed_.. classes"

    def on_entry(self):
        # TODO: log the state
        pass


@DeviceStateMachine.state_class
class failed_reboot_rebooting(failed):
    "While rebooting, power-cycling the device has failed multiple times"


@DeviceStateMachine.state_class
class failed_reboot_complete(failed):
    "While rebooting, device has been power-cycled multiple times, but the image has not run."

