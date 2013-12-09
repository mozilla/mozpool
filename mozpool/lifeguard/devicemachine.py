# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import datetime
from mozpool import config, statemachine, statedriver, async
from mozpool.bmm import api
from mozpool.db import exceptions
import mozpool.lifeguard


####
# State machine

class DeviceStateMachine(statemachine.StateMachine):

    def __init__(self, device_name, db):
        statemachine.StateMachine.__init__(self, 'device', device_name, db)
        self.device_name = device_name

    def read_state(self):
        return self.db.devices.get_machine_state(self.device_name)

    def write_state(self, new_state, timeout_duration):
        if timeout_duration is None:
            state_timeout = None
        else:
            state_timeout = datetime.datetime.now() + datetime.timedelta(seconds=timeout_duration)
        self.db.devices.set_machine_state(self.device_name, new_state, state_timeout)

    def read_counters(self):
        return self.db.devices.get_counters(self.device_name)

    def write_counters(self, counters):
        self.db.devices.set_counters(self.device_name, counters)


####
# Driver

class DeviceLogDBHandler(statedriver.DBHandler):

    object_type = 'device'


class LifeguardDriver(statedriver.StateDriver):
    """
    A driver for lifeguard.  This handles timeouts, as well as handling any
    events triggered externally.

    The server code sets up an instance of this object as mozpool.lifeguard.driver.
    """

    state_machine_cls = DeviceStateMachine
    logger_name = 'device'
    thread_name = 'LifeguardDriver'
    log_db_handler = DeviceLogDBHandler

    def __init__(self, db, poll_frequency=statedriver.POLL_FREQUENCY):
        statedriver.StateDriver.__init__(self, db, poll_frequency)
        self._imaging_server_id = None

        # set up the BMM API for use by machines
        self.api = api.API(db)

    def _get_machine(self, machine_name):
        machine = super(LifeguardDriver, self)._get_machine(machine_name)
        machine.api = self.api
        return machine

    def _get_timed_out_machine_names(self):
        return self.db.devices.list_timed_out(self.imaging_server_id)

    @property
    def imaging_server_id(self):
        if self._imaging_server_id is None:
            self._imaging_server_id = self.db.imaging_servers.get_id(config.get('server', 'fqdn'))
        return self._imaging_server_id

####
# Mixins

class AcceptBasicPleaseRequests(object):
    "Mixin to accept requests to self-test or enter maintenance mode"

    def on_please_self_test(self, args):
        self.machine.goto_state(start_self_test)

    def on_please_start_maintenance(self, args):
        self.machine.goto_state(start_maintenance)


class AcceptPleaseRequests(AcceptBasicPleaseRequests):
    "Mixin to also accept requests that assume a working device"

    def on_please_power_cycle(self, args):
        # clear out any "next image" so we don't accidentally reimage
        self.db.devices.set_next_image(self.machine.device_name, None, None)
        self.machine.goto_state(pc_power_cycling)

    def on_please_image(self, args):
        try:
            # verify it's possible (this raises an exception if not)
            self.db.devices.get_pxe_config(self.machine.device_name,
                                           args['image'])
            self.logger.info('setting next image to %s, boot config to %s' %
                             (args['image'], args['boot_config']))
            self.db.devices.set_next_image(self.machine.device_name,
                                   args['image'],
                                   args['boot_config'])
            self.machine.goto_state(start_pxe_boot)
        except exceptions.NotFound:
            self.logger.error('cannot image device')


class PowerCycleMixin(object):
    """
    Mixin for states that power-cycle the board.
    We first attempt to reboot via SUT agent, if present in the device's image.
    If there is a relay present, and there is no SUT agent or the SUT agent has
    failed a few times, fall back to the relay.
    If no relay, continue SUT attempts.
    Immediately fail if there is no SUT agent nor relay.
    """

    # to be filled in by subclasses:
    power_cycle_complete_state = None

    # wait for 60 seconds for a power cycle to succeed, and do this a bunch of
    # times.

    # failures when power-cycling via relay are likely a problem with the
    # network or relay board, so we want to retry until that's available.
    # WARNING: this timeout must be larger than the normal time to cycle a
    # device (3s for relay boards) times the number of devices per relay or
    # PDU (14 for relay boards).

    # reboot attempts via SUT are guaranteed to take less than 60 seconds
    # through socket timeouts.

    TIMEOUT = 60                    # must be greater than 42s; see above
    PERMANENT_FAILURE_COUNT = 200

    def setup_pxe(self):
        # hook for subclasses
        self.machine.api.clear_pxe.run(self.machine.device_name)

    def on_entry(self):
        # note that we do not try to use sut_reboot, as it is not reliable.
        # see bug 890933.
        has_relay = self.db.devices.get_relay_info(self.machine.device_name)
        if has_relay:
            self.relay_powercycle()
        else:
            self.logger.error('cannot power-cycle device: no relay')
            self.machine.goto_state(failed_power_cycling)

    def relay_powercycle(self):
        # kick off a power cycle on entry
        def powercycle_done(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'power_cycle_ok', {})
        self.setup_pxe()
        self.logger.info("initiating power cycle")
        self.machine.api.powercycle.start(powercycle_done, self.machine.device_name)

    def on_timeout(self):
        self.on_power_cycle_failed({})

    def on_power_cycle_failed(self, args):
        if (self.machine.increment_counter('power_cycling') >
            self.PERMANENT_FAILURE_COUNT):
            self.machine.goto_state(failed_power_cycling)
        else:
            self.machine.goto_state(self.state_name)

    def on_power_cycle_ok(self, args):
        self.machine.clear_counter('power_cycling')
        self.power_cycle_complete()

    def power_cycle_complete(self):
        """
        Subclasses can override this to do something more complex than going to
        power_cycle_complete_state
        """
        self.machine.goto_state(self.power_cycle_complete_state)


class ImagingResultMixin(object):

    def send_imaging_result(self, imaging_result):
        """
        Send the given imaging result to Mozpool.  This both inserts the result
        into the db and POSTs it to the Mozpool server, but does nothing if
        there is no attached request.
        """
        device_name = self.machine.device_name
        self.db.device_requests.set_result(device_name, imaging_result)

        # find out if this device was requested
        req_id = self.db.device_requests.get_by_device(device_name)
        if req_id is None:
            return

        # next, who do we talk to about this request?
        try:
            imaging_svr = self.db.requests.get_imaging_server(req_id)
        except exceptions.NotFound:
            return

        # tell mozpool we're finished.  This is a notification, so we really
        # don't care if it succeeds or not
        self.logger.info("sending imaging result '%s' to Mozpool" % imaging_result)
        mozpool_url = 'http://%s/api/request/%d/event/lifeguard_finished/' % (
                imaging_svr, req_id)
        def posted(result):
            if result.status_code != 200:
                self.logger.warn("got %d from Mozpool" % result.status_code)
        async.requests.post.start(posted, mozpool_url,
                data=json.dumps({'imaging_result': imaging_result}))


####
# Initial and steady states

@DeviceStateMachine.state_class
class new(AcceptPleaseRequests, statemachine.State):
    "This device is newly installed.  Begin by self-testing."

    TIMEOUT = 0

    def on_timeout(self):
        self.machine.goto_state(start_self_test)


@DeviceStateMachine.state_class
class unknown(AcceptPleaseRequests, statemachine.State):
    "This device is in an unknown state.  Await instructions."


@DeviceStateMachine.state_class
class locked_out(statemachine.State):
    """This device is handled outside of mozpool, and mozpool should not touch it.
    The device must be forced out of this state."""

@DeviceStateMachine.state_class
class troubleshooting(AcceptPleaseRequests, statemachine.State):
    """
    This device is in a troubleshooting state and will not timeout.
    A 'please_' event or force state must be used to move the device
    back into a 'normal' state.
    """

@DeviceStateMachine.state_class
class ready(AcceptPleaseRequests, statemachine.State):
    """
    This device is ready for use.  It may be attached to a mozpool request.
    While in this state, if no request is attached, lifeguard monitors the
    device periodically and takes corrective action if it fails.
    """

    # this must be greater than both the ping timeout (10s) and the sut_verify
    # timeout (30s).  It should be large, too, to keep load on the imaging server
    # to a reasonable level
    TIMEOUT = 600

    def on_entry(self):
        # first, if this device is in use by mozpool, don't check its status
        req_id = self.db.device_requests.get_by_device(self.machine.device_name)
        if req_id is not None:
            return

        # otherwise, either sut_verify, or ping, depending on the image capabilities
        if self.db.devices.has_sut_agent(self.machine.device_name):
            self.start_sut_verify()
        else:
            self.start_ping()

    def start_sut_verify(self):
        def sut_verified(success):
            if not success:
                self.logger.warning("device failed SUT verification")
                mozpool.lifeguard.driver.handle_event(self.machine.device_name,
                                                      'failed', {})
        self.machine.api.sut_verify.start(sut_verified, self.machine.device_name)

    def start_ping(self):
        def ping_complete(success):
            if not success:
                self.logger.warning("device failed ping check")
                mozpool.lifeguard.driver.handle_event(self.machine.device_name,
                                                      'failed', {})
        self.machine.api.ping.start(ping_complete, self.machine.device_name)

    def on_timeout(self):
        self.machine.goto_state(ready)

    def on_failed(self, args):
        # on failure, run a self-test.  Note that self-tests do not end with
        # 'operation_completed', so they will not accidentally report completion
        # to mozpool.
        self.machine.goto_state(start_self_test)


####
# Power Cycling

@DeviceStateMachine.state_class
class pc_power_cycling(PowerCycleMixin, statemachine.State):
    """
    A reboot has been requested, and the device is being power-cycled.  Once
    the power cycle is successful, go to state 'pc_rebooting'.
    """

    def power_cycle_complete(self):
        self.machine.goto_state(pc_rebooting)


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
class pc_sut_rebooting(statemachine.State):
    """
    We have rebooted the device via SUT.  The effect isn't immediate, though, so
    we give the device a short time to shut itself down.  Without this, it's possible
    to successfully run a SUT verify *before* the device reboots, which is not what
    we want!
    """

    TIMEOUT = 10

    def on_timeout(self):
        self.machine.goto_state(sut_verifying)


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
        self.machine.api.ping.start(ping_complete, self.machine.device_name)

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
        self.machine.goto_state(operation_complete)


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
class start_self_test(statemachine.State):
    """
    A self-test has been requested.  If a self-test PXE config exists for the
    device, set the device configuration and power cycle into the PXE states.
    If not, just power cycle; if the image has a SUT agent, it will
    automatically do some verification after booting.
    """

    def on_entry(self):
        self.machine.clear_counter()
        try:
            self.db.devices.get_pxe_config(self.machine.device_name,
                                           'self-test')
        except exceptions.NotFound:
            # can't self-test this device..
            self.machine.goto_state(pc_power_cycling)
        else:
            self.db.devices.set_next_image(self.machine.device_name, 'self-test', '')
            self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class start_maintenance(statemachine.State):
    """
    Maintenance mode has been requested.  Clear counters, set the device configuration,
    and get started.
    """

    def on_entry(self):
        self.machine.clear_counter()
        self.db.devices.set_next_image(self.machine.device_name, 'maintenance', '')
        self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class pxe_power_cycling(PowerCycleMixin, statemachine.State):
    """
    A PXE boot has been requested, and the device is being power-cycled.  Once
    the power cycle is successful, go to state 'pxe_booting'.
    """

    power_cycle_complete_state = 'pxe_booting'

    def setup_pxe(self):
        # set the pxe config based on the next image
        try:
            pxe_config = self.db.devices.get_pxe_config(self.machine.device_name)
        except exceptions.NotFound:
            self.logger.warning('no appropriate PXE config found')
            self.machine.goto_state(failed_pxe_booting)
            return
        self.logger.info("setting PXE config to %s" % (pxe_config,))
        self.machine.api.set_pxe.run(self.machine.device_name, pxe_config)


@DeviceStateMachine.state_class
class pxe_booting(statemachine.State):
    """
    The power has been cycled and we are waiting for the uboot to find its pxe config and
    begin the ubuntu live boot session.  When successful, the next state should be
    mobile_init_started.
    """

    # Startup seems to take about 90s; double that makes a good timeout.  There
    # are a number of ways this step could go wrong, so we allow a lot of
    # retries before calling it a failure.
    TIMEOUT = 180
    PERMANENT_FAILURE_COUNT = 30

    def on_mobile_init_started(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.api.clear_pxe.run(self.machine.device_name)
        self.machine.goto_state(mobile_init_started)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_pxe_booting)
        else:
            self.machine.goto_state(pxe_power_cycling)


@DeviceStateMachine.state_class
class mobile_init_started(statemachine.State):
    """
    Once mobile-init has started, its only job is to download and execute a second stage
    script as given by the pxe config.  Any timeouts here indicate trouble retrieving
    or executing the second stage
    """

    # This should take no time at all and there are not many failures this can get into
    # so we keep the timeout and failure count low
    TIMEOUT = 10
    PERMANENT_FAILURE_COUNT = 10

    def on_android_downloading(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.api.clear_pxe.run(self.machine.device_name)
        self.machine.goto_state(android_downloading)

    def on_b2g_downloading(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.api.clear_pxe.run(self.machine.device_name)
        self.machine.goto_state(b2g_downloading)

    def on_maint_mode(self, args):
        # note we do not clear the PXE config here, so it will
        # continue to boot into maintenance mode on subsequent reboots
        self.machine.clear_counter(self.state_name)
        # assume that maintenance has clobbered the image
        self.db.devices.set_image(self.machine.device_name, None, None)
        self.machine.goto_state(maintenance_mode)

    def on_self_test_running(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.api.clear_pxe.run(self.machine.device_name)
        # assume that the self test has clobbered the image
        self.db.devices.set_image(self.machine.device_name, None, None)
        self.db.devices.set_next_image(self.machine.device_name, None, None)
        self.machine.goto_state(self_test_running)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_mobile_init_started)
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
        self.db.devices.set_image(self.machine.device_name, None, None)
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
    the 'sut_verifying' state where it will wait for SUT to come up.
    """

    # Extracting takes 2m on a good day.  Give it plenty of leeway.  Funky
    # sdcards can cause this to fail, so it gets a few retries, but honestly,
    # this is an indication that the sdcard should be replaced
    TIMEOUT = 600
    PERMANENT_FAILURE_COUNT = 10

    def on_android_rebooting(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(sut_verifying)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_android_extracting)
        else:
            self.machine.goto_state(pxe_power_cycling)


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
        self.db.devices.set_image(self.machine.device_name, None, None)
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
    the 'sut_verifying' state to make sure the image comes up.
    """

    # Extracting takes 1m on a good day.  Give it plenty of leeway.  Funky
    # sdcards can cause this to fail, so it gets a few retries, but honestly,
    # this is an indication that the sdcard should be replaced
    TIMEOUT = 300
    PERMANENT_FAILURE_COUNT = 10

    def on_b2g_rebooting(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(sut_verifying)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_b2g_extracting)
        else:
            self.machine.goto_state(pxe_power_cycling)


####
# SUT Verifying

# This sequence of states checks the device using SUT.  It forms the final set
# of operations for several sequences above, and goes to the 'ready' state when
# it is finished.

@DeviceStateMachine.state_class
class sut_verifying(statemachine.State):
    """
    Verify that we can establish a connection to the device's SUT agent.
    This assumes that the device has a SUT agent on it.
    """

    # wait a bit over 20m total for the device to reboot and come up
    PERMANENT_FAILURE_COUNT = 30
    # power-cycling every 450s = 7.3m
    POWER_CYCLE_EVERY = 10
    # the SUT check can take up to 45s, so don't reduce this further
    TIMEOUT = 45

    def on_entry(self):
        def sut_verified(success):
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name,
                                                      'sut_verify_ok', {})
             # if not, wait for the timeout to occur, rather than immediately
             # re-checking
        self.machine.api.sut_verify.start(sut_verified, self.machine.device_name)

    def on_timeout(self):
        ctr = self.machine.increment_counter(self.state_name)
        if ctr > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_sut_verifying)
        elif ctr % self.POWER_CYCLE_EVERY == 0:
            self.machine.goto_state(sut_verify_power_cycle)
        else:
            self.machine.goto_state(self.state_name)

    def on_sut_verify_ok(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(sut_sdcard_verifying)


@DeviceStateMachine.state_class
class sut_verify_power_cycle(statemachine.State):
    """
    sut_verifying has failed a few times.  Power-cycle the device and try again.
    """

    PERMANENT_FAILURE_COUNT = 3
    TIMEOUT = 60                    # must be greater than 42s; see above

    def on_entry(self):
        def powercycle_done(success):
            # send the machine a power-cycle-ok event on success, and do nothing on failure (timeout)
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name, 'power_cycle_ok', {})
        self.machine.api.powercycle.start(powercycle_done, self.machine.device_name)

    def on_power_cycle_ok(self, args):
        self.machine.goto_state('sut_verifying')

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(failed_sut_verifying)
        else:
            self.machine.goto_state(self.state_name)

@DeviceStateMachine.state_class
class sut_sdcard_verifying(statemachine.State):
    """
    Verify that we can write a test file to the device's SD card.
    """

    PERMANENT_FAILURE_COUNT = 2
    # this should be greater than the sdcard timeout (195s)
    TIMEOUT = 200

    def on_entry(self):
        def sdcard_verified(success):
            if success:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name,
                                                      'sut_sdcard_ok', {})
            else:
                mozpool.lifeguard.driver.handle_event(self.machine.device_name,
                                                      'sut_sdcard_failed', {})
        self.machine.api.check_sdcard.start(sdcard_verified, self.machine.device_name)

    def on_timeout(self):
        self.on_sut_sdcard_failed({})

    def on_sut_sdcard_failed(self, args):
        if (self.machine.increment_counter(self.state_name) >
            self.PERMANENT_FAILURE_COUNT):
            self.machine.goto_state(failed_sut_sdcard_verifying)
        else:
            self.machine.goto_state(self.state_name)

    def on_sut_sdcard_ok(self, args):
        self.machine.clear_counter(self.state_name)
        self.machine.goto_state(operation_complete)


@DeviceStateMachine.state_class
class operation_complete(ImagingResultMixin, statemachine.State):
    """
    An intermediate state to wrap up an operation.  This takes care of some
    housekeeping before returning to 'ready'
    """

    TIMEOUT = 60

    def on_entry(self):
        # if there's a next_image, then the imaging is now complete, so set the
        # image and blank out the next image
        device_name = self.machine.device_name
        new_img = self.db.devices.get_next_image(device_name)
        if new_img['image']:
            self.db.devices.set_image(device_name,
                    new_img['image'], new_img['boot_config'])
            self.db.devices.set_next_image(device_name, None, None)

        # inform mozpool, if it cares
        self.send_imaging_result('complete')
        self.machine.goto_state(ready)

    def on_timeout(self):
        # re-enter this state in case we get stuck here by a server failure
        self.machine.goto_state(operation_complete)


####
# PXE Booting :: Maintenance mode

@DeviceStateMachine.state_class
class maintenance_mode(AcceptBasicPleaseRequests, statemachine.State):
    """
    The panda has successfully booted into maintenance mode, and has a waiting
    SSH prompt.  There is no timeout here; one of the 'please_' events must be used
    to move the device back into a 'normal' state.
    """


####
# PXE Booting :: Self-Test

@DeviceStateMachine.state_class
class self_test_running(AcceptBasicPleaseRequests, statemachine.State):
    """
    The panda has begun running self-tests.  The self-test script will log information
    about the device, but the only input this state will see is a self_test_ok event,
    or a timeout if the self-test fails.  This state allows another self-test to be
    initiated, or maintenance mode - useful, for example, if a faulty cable was replaced.
    """

    # let the test run for pretty much as long as it wants to
    TIMEOUT = 3600

    def on_timeout(self):
        self.machine.goto_state(failed_self_test)

    def on_self_test_ok(self, args):
        self.machine.goto_state(ready)

    def on_failed_self_test(self, args):
        self.machine.goto_state(failed_self_test)

####
# Failure states

class failed(AcceptBasicPleaseRequests, ImagingResultMixin, statemachine.State):
    """Parent class for failed_.. classes.  The only way out is a self-test or
    maintenance mode."""

    # by default, a failure will be indicated to mozpool with this imaging result.
    # subclasses can set this for other results
    imaging_result = 'failed-bad-device'

    # if true, this state should bounce immediately into a self-test operation
    try_self_test = False

    def on_entry(self):
        self.logger.error("device has failed: %s" % self.state_name)
        self.send_imaging_result(self.imaging_result)
        if self.try_self_test:
            self.machine.goto_state(start_self_test)


@DeviceStateMachine.state_class
class failed_power_cycling(failed):
    "The power-cycle operation itself has failed or timed out multiple times"

@DeviceStateMachine.state_class
class failed_pxe_booting(failed):
    "While PXE booting, the device repeatedly failed to contact the imaging server from the live image."

@DeviceStateMachine.state_class
class failed_mobile_init_started(failed):
    "While executing mobile-init, the device repeatedly failed to contact the imaging server from the live image."

@DeviceStateMachine.state_class
class failed_sut_verifying(failed):
    "Could not connect to SUT agent."
    try_self_test = True

@DeviceStateMachine.state_class
class failed_sut_sdcard_verifying(failed):
    "Failed to verify device's SD card."
    try_self_test = True

@DeviceStateMachine.state_class
class failed_android_downloading(failed):
    "While installing Android, the device timed out repeatedly while downloading Android"
    try_self_test = True

@DeviceStateMachine.state_class
class failed_android_extracting(failed):
    "While installing Android, the device timed out repeatedly while extracting Android"
    try_self_test = True

@DeviceStateMachine.state_class
class failed_android_pinging(failed):
    "While installing Android, the device timed out repeatedly while pinging the new image waiting for it to come up"
    try_self_test = True

@DeviceStateMachine.state_class
class failed_b2g_downloading(failed):
    "While installing B2G, the device timed out repeatedly while downloading B2G"
    try_self_test = True

@DeviceStateMachine.state_class
class failed_b2g_extracting(failed):
    "While installing B2G, the device timed out repeatedly while extracting B2G"
    try_self_test = True

@DeviceStateMachine.state_class
class failed_b2g_pinging(failed):
    "While installing B2G, the device timed out repeatedly while pinging the new image waiting for it to come up"
    try_self_test = True

@DeviceStateMachine.state_class
class failed_self_test(failed):
    "While installing B2G, the device timed out repeatedly while pinging the new image waiting for it to come up"

