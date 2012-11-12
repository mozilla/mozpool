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

    def handle_event(self, device_name, event, args):
        """
        Handle an event for a particular device, with optional arguments
        specific to the event.
        """
        machine = self._get_machine(device_name)
        machine.handle_event(event, args)

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

class AcceptPleaseRequests(object):

    def on_please_power_cycle(self, args):
        self.machine.goto_state(pc_power_cycling)


    def on_please_pxe_boot(self, args):
        print args
        data.set_device_config(self.machine.device_name,
                args['pxe_config'],
                args['boot_config'])
        self.machine.goto_state(pxe_power_cycling)

class PowerCycleMixin(object):

    # to be filled in by subclasses:
    power_cycle_complete_state = None

    # wait for 60 seconds for a power cycle to succeed, and do this a bunch of
    # times; failures here are likely a problem with the network or relay
    # board, so we want to retry until that's available.  WARNING: this timeout
    # must be larger than the normal time to cycle a device (3s for relay boards)
    # times the number of devices per relay or PDU (14 for relay boards).

    TIMEOUT = 60                    # must be greater than 42s; see above
    PERMANENT_FAILURE_COUNT = 200

    # TODO: add a *second* counter to count number of round-trips into this
    # state, maybe just based on the state name?

    def setup_pxe(self):
        # hook for subclasses
        bmm_api.clear_pxe(self.machine.device_name)

    def on_entry(self):
        # kick off a power cycle on entry
        def powercycle_done(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'power_cycle_ok', {})
        self.setup_pxe()
        bmm_api.start_powercycle(self.machine.device_name, powercycle_done)

    def on_timeout(self):
        if self.machine.increment_counter('power_cycling') > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_power_cycling)
        else:
            self.machine.goto_state(self.state_name)

    def on_power_cycle_ok(self, args):
        self.machine.clear_counter('power_cycling')
        self.machine.goto_state(self.power_cycle_complete_state)


####
# Initial and steady states

@DeviceStateMachine.state_class
class new(AcceptPleaseRequests, statemachine.State):
    "This device is newly installed.  Await instructions."


@DeviceStateMachine.state_class
class unknown(AcceptPleaseRequests, statemachine.State):
    "This device is in an unknown state.  Await instructions."


@DeviceStateMachine.state_class
class ready(AcceptPleaseRequests, statemachine.State):
    "This device is production-ready."

    TIMEOUT = 300

    def on_entry(self):
        self.machine.clear_counter()
        def ping_complete(success):
            # if the ping succeeds, great - wait for a timeout.  Otherwise, try to power-cycle.
            # TODO: not sure this is a great idea, but here goes..
            if not success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'ready_ping_failed', {})
        bmm_api.start_ping(self.machine.device_name, ping_complete)

    def on_timeout(self):
        # re-enter the 'ready' state, beginning the ping again
        self.machine.goto_state(ready)

    def on_ready_ping_failed(self, args):
        self.machine.goto_state(pc_power_cycling)


####
# Power Cycling

@DeviceStateMachine.state_class
class pc_power_cycling(PowerCycleMixin, statemachine.State):
    """
    A reboot has been requested, and the device is being power-cycled.  Once
    the power cycle is successful, go to state 'pc_pinging'.
    """

    power_cycle_complete_state = 'pc_pinging'


@DeviceStateMachine.state_class
class pc_pinging(statemachine.State):
    """
    A reboot has been requested, and the power cycle is complete.  Ping until
    successful, then go to state 'ready'
    """

    # ping every 10s, failing 12 times
    TIMEOUT = 10
    PERMANENT_FAILURE_COUNT = 12

    def on_entry(self):
        def ping_complete(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'ping_ok', {})
        bmm_api.start_ping(self.machine.device_name, ping_complete)

    def on_timeout(self):
        if self.machine.increment_counter('pc_pinging') > self.PERMANENT_FAILURE_COUNT:
            # after enough ping failures, try rebooting again (and clear the ping counter)
            self.machine.clear_counter('pc_pinging')
            self.machine.goto_state(pc_power_cycling)
        else:
            # otherwise, re-enter this state and ping again
            self.machine.goto_state(pc_pinging)

    def on_ping_ok(self, args):
        self.machine.clear_counter('pc_pinging')
        self.machine.goto_state(ready)

####
# PXE Booting

# Every PXE boot process starts off the same way: set up the PXE config and
# power-cycle.  However, the events from scripts on the device itself can
# branch execution in a number of directions, based on the operation being
# performed.

# TODO: better handling for timeouts to disambiguate the failure modes

@DeviceStateMachine.state_class
class pxe_power_cycling(PowerCycleMixin, statemachine.State):
    """
    A PXE boot has been requested, and the device is being power-cycled.  Once
    the power cycle is successful, go to state 'pxe_starting'.
    """

    power_cycle_complete_state = 'pxe_booting'

    def setup_pxe(self):
        # set the pxe config based on what's in the DB
        cfg = data.device_config(self.machine.device_name)
        bmm_api.set_pxe(self.machine.device_name,
                cfg['pxe_config'],
                cfg['config'])


@DeviceStateMachine.state_class
class pxe_booting(statemachine.State):
    """
    The power has been cycled and we are waiting for the uboot image to start
    and run its second stage.  When successful, the next state is based on the
    event received from the second stage.
    """

    # TODO: convince mobile-init.sh to repot an event here)

    # Startup seems to take about 90s; double that makes a good timeout.
    TIMEOUT = 180

    def on_android_downloading(self, args):
        bmm_api.clear_pxe(self.machine.device_name)
        self.machine.goto_state(android_downloading)

    def on_timeout(self):
        self.machine.goto_state(pxe_power_cycling)


####
# PXE Booting :: Android Installation

@DeviceStateMachine.state_class
class android_downloading(statemachine.State):
    """
    The second-stage script is downloading the Android artifacts.  When
    complete, it will send an event and go into the 'android_extracting' state.
    """

    # Downloading takes about 30s.  Allow a generous multiple of that to handle
    # moments of high load or bigger images.
    TIMEOUT = 180

    def on_android_extracting(self, args):
        self.machine.goto_state(android_extracting)

    def on_timeout(self):
        self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class android_extracting(statemachine.State):
    """
    The second-stage script is extracting the Android artifacts onto the
    sdcard.  When this is complete, the script will send an event and go into
    the 'android_rebooting' state.
    """

    # Extracting takes 2m on a good day.  Give it plenty of leeway.
    TIMEOUT = 600

    def on_android_rebooting(self, args):
        self.machine.goto_state(android_rebooting)

    def on_timeout(self):
        self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class android_rebooting(statemachine.State):
    """
    The second-stage script has rebooted the device.  This state waits a short
    time, then begins pinging the device.  The wait is to avoid a false positive
    ping from the board *before* it has rebooted.
    """

    # A panda seems to take about 20s to boot, so we'll round that up a bit
    TIMEOUT = 40

    def on_timeout(self):
        self.machine.goto_state(android_pinging)


@DeviceStateMachine.state_class
class android_pinging(statemachine.State):
    """
    A reboot has been requested, and the power cycle is complete.  Ping until
    successful, then go to state 'ready'
    """

    # ping every 10s, failing 12 times (2 minutes total)
    TIMEOUT = 10
    PERMANENT_FAILURE_COUNT = 12

    def on_entry(self):
        def ping_complete(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'ping_ok', {})
        bmm_api.start_ping(self.machine.device_name, ping_complete)

    def on_timeout(self):
        if self.machine.increment_counter('android_pinging') > self.PERMANENT_FAILURE_COUNT:
            # after enough ping failures, try rebooting again (and clear the ping counter)
            self.machine.clear_counter('android_pinging')
            self.machine.goto_state(pxe_power_cycling)
        else:
            # otherwise, re-enter this state and ping again
            self.machine.goto_state(android_pinging)

    def on_ping_ok(self, args):
        self.machine.clear_counter('android_pinging')
        self.machine.goto_state(ready)

    # TODO: also try a SUT agent connection here

####
# Failure states

class failed(statemachine.State):
    "Parent class for failed_.. classes"

    def on_entry(self):
        self.logger.error("device has failed")


@DeviceStateMachine.state_class
class failed_power_cycling(failed):
    "The power-cycle operation itself has failed or timed out multiple times"


@DeviceStateMachine.state_class
class failed_reboot_complete(failed):
    "While rebooting, device has been power-cycled multiple times, but the image has not run."

