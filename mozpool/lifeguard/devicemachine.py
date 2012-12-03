# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
from mozpool import config, statemachine, statedriver
from mozpool.bmm import api as bmm_api
from mozpool.db import data
import mozpool.lifeguard


####
# State machine

class DeviceStateMachine(statemachine.StateMachine):

    def __init__(self, device_name):
        statemachine.StateMachine.__init__(self, 'device', device_name)
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
# Driver

class LifeguardDriver(statedriver.StateDriver):
    """
    A driver for lifeguard.  This handles timeouts, as well as handling any
    events triggered externally.

    The server code sets up an instance of this object as mozpool.lifeguard.driver.
    """

    state_machine_cls = DeviceStateMachine
    logger_name = 'device'
    thread_name = 'LifeguardDriver'

    def __init__(self, poll_frequency=statedriver.POLL_FREQUENCY):
        statedriver.StateDriver.__init__(self, poll_frequency)
        self.imaging_server_id = data.find_imaging_server_id(
            config.get('server', 'fqdn'))

    def _get_timed_out_machine_names(self):
        return data.get_timed_out_devices(self.imaging_server_id)

    def conditional_state_change(self, device_name, old_state, new_state,
                                 new_pxe_config, new_boot_config):
        """
        Transition to NEW_STATE only if the device is in OLD_STATE.
        Simultaneously set the PXE config and boot config as described, or
        clears the PXE config if new_pxe_config is None.
        Returns True on success, False on failure.
        """
        def call_first():
            if new_pxe_config is None:
                bmm_api.clear_pxe(device_name)
            else:
                bmm_api.set_pxe(device_name, new_pxe_config, new_boot_config)
        return statedriver.StateDriver.conditional_state_change(
            self, device_name, old_state, new_state, call_first)


####
# Mixins

class AcceptPleaseRequests(object):

    def on_please_power_cycle(self, args):
        self.machine.goto_state(pc_power_cycling)


    def on_please_pxe_boot(self, args):
        self.logger.info('writing pxe_config %s, boot config %s to db' % (args['pxe_config'], args['boot_config']))
        data.set_device_config(self.machine.device_name,
                args['pxe_config'],
                args['boot_config'])
        self.machine.goto_state(start_pxe_boot)


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
class free(AcceptPleaseRequests, statemachine.State):
    "This device is not in use and available for mozpool requests."

@DeviceStateMachine.state_class
class locked_out(statemachine.State):
    """This device is handled outside of mozpool, and mozpool should not touch it.
    The device must be forced out of this state."""

@DeviceStateMachine.state_class
class ready(AcceptPleaseRequests, statemachine.State):
    """
    This device has been assigned via mozpool and is ready for use by the
    client.
    """

    TIMEOUT = 60

    # At one point, this state pinged devices in this state and power-cycled
    # them when they failed.  This resulted in a lot of unnecessary power cycles
    # for devices running "flaky" images, with no real benefit.

    def on_free(self, args):
        self.machine.goto_state(free)

    def on_timeout(self):
        # It's possible that we can get into this state after a request has
        # terminated, e.g., if the request is returned but the device is
        # still booting (since we want to continue through all the states).
        # Check for that here and return to free if necessary.
        if data.get_request_for_device(self.machine.device_name):
            self.machine.goto_state(ready)
        else:
            self.logger.warn('in ready state but not assigned to a request; '
                             'moving to free state')
            self.machine.goto_state(free)


####
# Power Cycling

@DeviceStateMachine.state_class
class pc_power_cycling(PowerCycleMixin, statemachine.State):
    """
    A reboot has been requested, and the device is being power-cycled.  Once
    the power cycle is successful, go to state 'pc_pinging'.
    """

    power_cycle_complete_state = 'pc_rebooting'


@DeviceStateMachine.state_class
class pc_rebooting(statemachine.State):
    """
    We have power-cycled the device.  This state waits a short time for uboot
    to start and boot from the sdcard, then begins pinging the device.  The
    wait is to avoid a false positive ping from uboot, rather than the image
    itself.
    """

    # The u-boot loader is also pingable, so we want to be very sure we don't get
    # a false positive from it.  So, this is quite a bit longer than strictly
    # necessary, but gives enough time to reboot, run u-boot, and then start b2g.
    TIMEOUT = 120

    def on_timeout(self):
        self.machine.goto_state(pc_pinging)


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

# There are several failure counters used here:
#
# * power_cycling -- used internally by PowerCycleMixin to keep trying to cycle
#   the power
# * ping -- count of ping failures; some are expected, until the device is up
#
# The others are named after the step, and count the number of times the step
# has failed (timed out unexpectedly).  Each such counter is cleared when the
# step completes successfully.

@DeviceStateMachine.state_class
class start_pxe_boot(statemachine.State):
    """
    A PXE boot has been requested.  Clear counters and get started.
    """

    def on_entry(self):
        self.machine.clear_counter()
        self.machine.goto_state(pxe_power_cycling)

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
                cfg['boot_config'])


@DeviceStateMachine.state_class
class pxe_booting(statemachine.State):
    """
    The power has been cycled and we are waiting for the uboot image to start
    and run its second stage.  When successful, the next state is based on the
    event received from the second stage.
    """

    # TODO: convince mobile-init.sh to report an event here - bug 811316

    # Startup seems to take about 90s; double that makes a good timeout.  There
    # are a number of ways this step could go wrong, so we allow a lot of
    # retries before calling it a failure.
    TIMEOUT = 180
    PERMANENT_FAILURE_COUNT = 30

    def on_android_downloading(self, args):
        self.machine.clear_counter(self.state_name)
        bmm_api.clear_pxe(self.machine.device_name)
        self.machine.goto_state(android_downloading)

    def on_b2g_downloading(self, args):
        self.machine.clear_counter(self.state_name)
        bmm_api.clear_pxe(self.machine.device_name)
        self.machine.goto_state(b2g_downloading)

    def on_maint_mode(self, args):
        # note we do not clear the PXE config here, so it will
        # continue to boot into maintenance mode
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(maintenance_mode)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_pxe_booting)
        else:
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
    # moments of high load or bigger images.  Failures here are likely a misconfig, 
    # so they aren't retried very many times
    TIMEOUT = 180
    PERMANENT_FAILURE_COUNT = 3

    def on_android_extracting(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(android_extracting)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_android_downloading)
        else:
            self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class android_extracting(statemachine.State):
    """
    The second-stage script is extracting the Android artifacts onto the
    sdcard.  When this is complete, the script will send an event and go into
    the 'android_rebooting' state.
    """

    # Extracting takes 2m on a good day.  Give it plenty of leeway.  Funky
    # sdcards can cause this to fail, so it gets a few retries, but honestly,
    # this is an indication that the sdcard should be replaced
    TIMEOUT = 600
    PERMANENT_FAILURE_COUNT = 10

    def on_android_rebooting(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(android_rebooting)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_android_extracting)
        else:
            self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class android_rebooting(statemachine.State):
    """
    The second-stage script has rebooted the device.  This state waits a short
    time, then begins pinging the device.  The wait is to avoid a false positive
    ping from the board *before* it has rebooted.
    """

    # The u-boot loader is also pingable, so we want to be very sure we don't get
    # a false positive from it.  So, this is quite a bit longer than strictly
    # necessary, but gives enough time to reboot, run u-boot, and then start Android
    TIMEOUT = 120

    def on_timeout(self):
        self.machine.goto_state(android_pinging)


@DeviceStateMachine.state_class
class android_pinging(statemachine.State):
    """
    A reboot has been requested, and the power cycle is complete.  Ping until
    successful, then go to state 'ready'
    """

    # ping every 10s, failing 12 times (2 minutes total).  If the whole process fails here
    # a few times, then most likely the image is bogus, so that's a permanent failure.
    TIMEOUT = 10
    PING_FAILURES = 12
    PERMANENT_FAILURE_COUNT = 4

    def on_entry(self):
        def ping_complete(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'ping_ok', {})
        bmm_api.start_ping(self.machine.device_name, ping_complete)

    def on_timeout(self):
        # this is a little tricky - android_pinging tracks a few tries to ping this device, so
        # when that counter expires, then we assume the device has not imaged correctly and
        # retry; *that* failure is counted against PERMANENT_FAILURE_COUNT.
        if self.machine.increment_counter('ping') > self.PERMANENT_FAILURE_COUNT:
            self.machine.clear_counter('ping')
            if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
                self.machine.goto_state(failed_android_pinging)
            else:
                self.machine.goto_state(pxe_power_cycling)
        else:
            self.machine.goto_state(android_pinging)

    def on_ping_ok(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.clear_counter('ping')
        self.machine.goto_state(ready)

    # TODO: also try a SUT agent connection here (mcote)

####
# PXE Booting :: B2G Installation

@DeviceStateMachine.state_class
class b2g_downloading(statemachine.State):
    """
    The second-stage script is downloading the B2G artifacts.  When
    complete, it will send an event and go into the 'b2g_extracting' state.
    """

    # Downloading takes about 30s.  Allow a generous multiple of that to handle
    # moments of high load or bigger images.  Failures here are likely a misconfig, 
    # so they aren't retried very many times
    TIMEOUT = 180
    PERMANENT_FAILURE_COUNT = 3

    def on_b2g_extracting(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(b2g_extracting)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_b2g_downloading)
        else:
            self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class b2g_extracting(statemachine.State):
    """
    The second-stage script is extracting the B2G artifacts onto the
    sdcard.  When this is complete, the script will send an event and go into
    the 'b2g_rebooting' state.
    """

    # Extracting takes 1m on a good day.  Give it plenty of leeway.  Funky
    # sdcards can cause this to fail, so it gets a few retries, but honestly,
    # this is an indication that the sdcard should be replaced
    TIMEOUT = 300
    PERMANENT_FAILURE_COUNT = 10

    def on_b2g_rebooting(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(b2g_rebooting)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_b2g_extracting)
        else:
            self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class b2g_rebooting(statemachine.State):
    """
    The second-stage script has rebooted the device.  This state waits a short
    time, then begins pinging the device.  The wait is to avoid a false positive
    ping from the board *before* it has rebooted.
    """

    # The u-boot loader is also pingable, so we want to be very sure we don't get
    # a false positive from it.  So, this is quite a bit longer than strictly
    # necessary, but gives enough time to reboot, run u-boot, and then start b2g.
    TIMEOUT = 120

    def on_timeout(self):
        self.machine.goto_state(b2g_pinging)


@DeviceStateMachine.state_class
class b2g_pinging(statemachine.State):
    """
    A reboot has been requested, and the power cycle is complete.  Ping until
    successful, then go to state 'ready'
    """

    # TODO: factor out into a mixin to combine with android_pinging

    # ping every 10s, failing 12 times (2 minutes total).  If the whole process fails here
    # a few times, then most likely the image is bogus, so that's a permanent failure.
    TIMEOUT = 10
    PING_FAILURES = 12
    PERMANENT_FAILURE_COUNT = 4

    def on_entry(self):
        def ping_complete(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'ping_ok', {})
        bmm_api.start_ping(self.machine.device_name, ping_complete)

    def on_timeout(self):
        # this is a little tricky - b2g_pinging tracks a few tries to ping this device, so
        # when that counter expires, then we assume the device has not imaged correctly and
        # retry; *that* failure is counted against PERMANENT_FAILURE_COUNT.
        if self.machine.increment_counter('ping') > self.PERMANENT_FAILURE_COUNT:
            self.machine.clear_counter('ping')
            if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
                self.machine.goto_state(failed_b2g_pinging)
            else:
                self.machine.goto_state(pxe_power_cycling)
        else:
            self.machine.goto_state(b2g_pinging)

    def on_ping_ok(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.clear_counter('ping')
        self.machine.goto_state(ready)

    # TODO: also try a SUT agent connection here (mcote)

####
# PXE Booting :: Maintenance Mode

@DeviceStateMachine.state_class
class maintenance_mode(AcceptPleaseRequests, statemachine.State):
    """
    The panda has successfully booted into maintenance mode, and has a waiting
    SSH prompt.  There is no timeout here; one of the 'please_' events must be used
    to move the device back into a 'normal' state.
    """


####
# Failure states

class failed(AcceptPleaseRequests, statemachine.State):
    "Parent class for failed_.. classes"

    def on_entry(self):
        self.logger.error("device has failed: %s" % self.state_name)


@DeviceStateMachine.state_class
class failed_power_cycling(failed):
    "The power-cycle operation itself has failed or timed out multiple times"

@DeviceStateMachine.state_class
class failed_pxe_booting(failed):
    "While PXE booting, the device repeatedly failed to contact the imaging server from the live image."

@DeviceStateMachine.state_class
class failed_android_downloading(failed):
    "While installing Android, the device timed out repeatedly while downloading Android"

@DeviceStateMachine.state_class
class failed_android_extracting(failed):
    "While installing Android, the device timed out repeatedly while extracting Android"

@DeviceStateMachine.state_class
class failed_android_pinging(failed):
    "While installing Android, the device timed out repeatedly while pinging the new image waiting for it to come up"

@DeviceStateMachine.state_class
class failed_b2g_downloading(failed):
    "While installing B2G, the device timed out repeatedly while downloading B2G"

@DeviceStateMachine.state_class
class failed_b2g_extracting(failed):
    "While installing B2G, the device timed out repeatedly while extracting B2G"

@DeviceStateMachine.state_class
class failed_b2g_pinging(failed):
    "While installing B2G, the device timed out repeatedly while pinging the new image waiting for it to come up"

