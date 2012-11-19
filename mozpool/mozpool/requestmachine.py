# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import random
import urllib

from mozpool import config, statemachine, statedriver
from mozpool.db import data, logs


####
# State machine

# FIXME: Very similar to DeviceStateMachine; refactor.

class RequestStateMachine(statemachine.StateMachine):

    def __init__(self, request_id):
        statemachine.StateMachine.__init__(self, 'request', request_id)
        self.request_id = request_id

    def read_state(self):
        state, timeout, counters = data.get_request_state(self.request_id)
        return state

    def write_state(self, new_state, timeout_duration):
        if timeout_duration:
            state_timeout = (datetime.datetime.now() +
                             datetime.timedelta(seconds=timeout_duration))
        else:
            state_timeout = None
        data.set_request_state(self.request_id, new_state, state_timeout)

    def read_counters(self):
        state, timeout, counters = data.get_request_state(self.request_id)
        return counters

    def write_counters(self, counters):
        data.set_request_counters(self.request_id, counters)


####
# Driver

class MozpoolDriver(statedriver.StateDriver):
    """
    The server code sets up an instance of this object as
    mozpool.mozpool.driver.
    """

    state_machine_cls = RequestStateMachine
    logger_name = 'request'
    thread_name = 'MozpoolDriver'

    def __init__(self, poll_frequency=statedriver.POLL_FREQUENCY):
        statedriver.StateDriver.__init__(self, poll_frequency)
        self.imaging_server_id = data.find_imaging_server_id(
            config.get('server', 'fqdn'))

    def _get_timed_out_machine_names(self):
        return data.get_timed_out_requests(self.imaging_server_id)

    def _tick(self):
        for request_id in data.get_expired_requests(self.imaging_server_id):
            self.handle_event(request_id, 'expire', None)


####
# Mixins

class Closable(object):

    def on_close(self, args):
        self.machine.goto_state(closed)


class Expirable(object):

    def on_expire(self, args):
        self.machine.goto_state(expired)


class ClearDeviceRequests(object):

    def on_entry(self):
        data.clear_device_request(self.machine.request_id)


@RequestStateMachine.state_class
class new_request(Closable, Expirable, statemachine.State):
    "New request; no action taken yet."

    def on_find_device(self, args):
        self.machine.goto_state(finding_device)


@RequestStateMachine.state_class
class finding_device(Closable, Expirable, statemachine.State):
    """
    Assign a device. If this is a request for a specific device,
    fail immediately if the device is busy. If a request for 'any',
    and no devices available, try a few times, with a delay between.

    FIXME: Better to differentiate the finding state (might take a
    few tries to find a free device) from the overall time to allocate a
    device (client might not want to wait more than X seconds).
    """

    TIMEOUT = 10
    MAX_ANY_REQUESTS = 12
    MAX_SPECIFIC_REQUESTS = 1

    def on_entry(self):
        self.find_device()

    def on_timeout(self):
        self.find_device()

    def find_device(self):
        # FIXME: refactor.
        device_name = None
        count = self.machine.increment_counter(self.state_name)
        request = data.dump_requests(self.machine.request_id)[0]
        if request['requested_device'] == 'any':
            free_devices = data.get_unassigned_ready_devices()
            if free_devices:
                device_id = random.randint(0, len(free_devices) - 1)
                device_name = free_devices[device_id]
                self.logger.info('assigning device %s' % device_name)
            else:
                self.logger.info('no free devices')
        else:
            device_name = request['requested_device']
            self.logger.info('assigning requested device %s' % device_name)

        if device_name and data.reserve_device(self.machine.request_id,
                                               device_name):
            self.logger.info('request succeeded')
            self.machine.goto_state(contacting_lifeguard)
        else:
            self.logger.warn('request failed!')
            if request['requested_device'] == 'any':
                if count >= self.MAX_ANY_REQUESTS:
                    self.machine.goto_state(device_not_found)
            else:
                if count >= self.MAX_SPECIFIC_REQUESTS:
                    self.machine.goto_state(device_busy)


@RequestStateMachine.state_class
class contacting_lifeguard(Closable, Expirable, statemachine.State):
    "Contacting device's lifeguard server to request reimage/reboot."

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 5

    def on_entry(self):
        if self.contact_lifeguard():
            self.machine.goto_state(pending)
            return
        counters = self.machine.read_counters()
        if counters.get(self.state_name, 0) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(device_not_found)

    def on_timeout(self):
        self.machine.increment_counter(self.state_name)
        self.machine.goto_state(contacting_lifeguard)

    def contact_lifeguard(self):
        device_request_data = {}
        request_config = data.request_config(self.machine.request_id)
        if request_config['boot_config']:
            event = 'please_pxe_boot'
            device_request_data['boot_config'] = request_config['boot_config']
        else:
            event = 'please_power_cycle'

        device_url = 'http://%s/api/device/%s/event/%s/' % (
            data.get_server_for_request(self.machine.request_id),
            request_config['assigned_device'], event)
        try:
            urllib.urlopen(device_url, json.dumps(device_request_data))
        except IOError:
            logs.request_logs.add(self.machine.request_id,
                                  "could not contact lifeguard server at %s" %
                                  device_url)
            return False
        return True


@RequestStateMachine.state_class
class pending(Closable, Expirable, statemachine.State):
    "Request is pending while a device is located and prepared."

    TIMEOUT = 10
    PERMANENT_FAILURE_COUNT = 60

    def on_timeout(self):
        # FIXME: go back to earlier state if request failed
        counter = self.machine.increment_counter(self.state_name)
        request_config = data.request_config(self.machine.request_id)
        device_name = request_config['assigned_device']
        device_state = data.device_status(device_name)['state']
        if device_state == 'ready':
            self.machine.goto_state(request_ready)
        elif counter > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(device_not_found)
        else:
            self.machine.goto_state(pending)


@RequestStateMachine.state_class
class request_ready(Closable, Expirable, statemachine.State):
    "Device has been prepared and is ready for use."


@RequestStateMachine.state_class
class expired(Closable, ClearDeviceRequests, statemachine.State):
    "Request has expired."


@RequestStateMachine.state_class
class closed(ClearDeviceRequests, statemachine.State):
    "Device was returned and request has been closed."


@RequestStateMachine.state_class
class device_not_found(Closable, Expirable, ClearDeviceRequests,
                       statemachine.State):
    "No working unassigned device could be found."


@RequestStateMachine.state_class
class device_busy(Closable, Expirable, ClearDeviceRequests,
                  statemachine.State):
    "The requested device is already assigned."
