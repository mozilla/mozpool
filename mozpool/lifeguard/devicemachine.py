# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from mozpool.db import data
from mozpool import statemachine
from mozpool.bmm import api as bmm_api

class DeviceStateMachine(statemachine.StateMachine):

    def __init__(self, device_name, device_id):
        statemachine.StateMachine.__init__(self, "device %s" % device_name)
        self.device_name = device_name
        self.device_id = device_id

    def read_state(self):
        return data.board_status(self.device_name)

    def write_state(self, new_state, timeout_duration):
        return data.update_board(self.device_id, dict(status=new_state))

    def read_counters(self):
        return {} # TODO: temp pending a schema change

    def write_counters(self, new_state, timeout_duration):
        return # TODO: temp pending a schema change


####
# Mixins

class AllowReboot(object):

    @statemachine.event_method('rq-reboot')
    def on_rq_reboot(self):
        self.goto_state(pc_rebooting)


####
# Initial and steady states

@DeviceStateMachine.state_class
class new(AllowReboot, statemachine.State):
    "This board is newly installed.  Await instructions."


@DeviceStateMachine.state_class
class unknown(AllowReboot, statemachine.State):
    "This board is in an unknown state.  Await instructions."


@DeviceStateMachine.state_class
class ready(AllowReboot, statemachine.State):
    "This board is production-ready."

    TIMEOUT = 300

    ## TODO: polling stuff isn't implemented yet

    def on_entry(self):
        self.clear_counter()
        start_polling()

    def on_exit(self):
        stop_polling()

    @statemachine.timeout_method(TIMEOUT)
    def on_timeout(self):
        self.goto_state(ready)

    @statemachine.event_method('poll-ok')
    def on_poll_ok(self):
        pass # wait for the timeout to expire, rather than immediately re-polling

    @statemachine.event_method('poll-failure')
    def on_poll_failure(self):
        self.goto_state(pc_rebooting)


####
# Power Cycling

@DeviceStateMachine.state_class
class pc_rebooting(statemachine.State):
    "A reboot has been requested, and the board is being power-cycled."

    # wait for 60 seconds for a poer cycle to succeed, and do this a bunch of
    # times; failures here are likely a problem with the network or relay board,
    # so we want to retry until that's available.

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 200

    def on_entry(self):
        # TODO: remove symlink

        # kick off a power cycle on entry, and send ourselves a power-cycle-ok
        # event on success
        def powercycle_done(success):
            if success:
                self.machine.handle_event('power-cycle-ok')
        bmm_api.start_powercycle(self.machine.machine_name, powercycle_done)

    @statemachine.timeout_method(TIMEOUT)
    def on_timeout(self):
        if self.increment_counter('pc_rebooting') > self.PERMANENT_FAILURE_COUNT:
            self.goto_state(failed_reboot_rebooting)
        else:
            self.goto_state(pc_rebooting)

    @statemachine.event_method('power-cycle-ok')
    def on_power_cycle_ok(self):
        self.clear_counter('pc_rebooting')
        self.goto_state(pc_complete)


@DeviceStateMachine.state_class
class pc_complete(statemachine.State):
    "A reboot has been requested, and the power cycle is complete."

    # give the image ample time to come up and tell us that it's running, but if
    # that doesn't work after a few reboots, the image itself is probably bad
    TIMEOUT = 600
    PERMANENT_FAILURE_COUNT = 10

    @statemachine.timeout_method(TIMEOUT)
    def on_timeout(self):
        if self.increment_counter('pc_complete') > self.PERMANENT_FAILURE_COUNT:
            self.goto_state(failed_reboot_complete)
        else:
            self.goto_state(pc_rebooting)

    # TODO: not clear how to know the image is running -- ping?
    # https://github.com/jedie/python-ping/blob/master/ping.py
    @statemachine.event_method('image-running')
    def on_image_running(self):
        self.clear_counter('pc_complete')
        self.goto_state(ready)

####
# Failure states

class failed(AllowReboot, statemachine.State):
    "Parent class for failed_.. classes"

    def on_entry(self):
        # TODO: log the state
        pass


@DeviceStateMachine.state_class
class failed_reboot_rebooting(failed):
    "While rebooting, power-cycling the board has failed multiple times"


@DeviceStateMachine.state_class
class failed_reboot_complete(failed):
    "While rebooting, board has been power-cycled multiple times, but the image has not run."

