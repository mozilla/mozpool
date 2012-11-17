# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import random
import urllib
from mozpool import config, statemachine, statedriver
from mozpool.db import data, logs


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


class MozpoolDriver(statedriver.StateDriver):

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


@RequestStateMachine.state_class
class new(Closable, Expirable, statemachine.State):
    "New request; no action taken yet."

    def on_find_device(self, args):
        self.machine.goto_state(findingdevice)


@RequestStateMachine.state_class
class findingdevice(Closable, Expirable, statemachine.State):
    "Assign device."

    TIMEOUT = 60
    MAX_ANY_REQUESTS = 3
    MAX_SPECIFIC_REQUESTS = 1

    def on_entry(self):
        self.find_device()

    def on_timeout(self):
        self.find_device()

    def find_device(self):
        count = self.machine.increment_counter(self.state_name)
        request = data.dump_requests(self.machine.request_id)[0]
        if request['requested_device'] == 'any':
            free_devices = data.get_unassigned_devices()
            if not free_devices:
                return  # retry
            device_name = free_devices[random.randint(0, len(free_devices) - 1)]
        else:
            device_name = request['requested_device']

        if data.reserve_device(self.machine.request_id, device_name):
            self.machine.goto_state(contactinglifeguard)
        else:
            if request['requested_device'] == 'any':
                if count >= self.MAX_ANY_REQUESTS:
                    self.machine.goto_state(devicenotfound)
            else:
                if count >= self.MAX_SPECIFIC_REQUESTS:
                    self.machine.goto_state(devicebusy)


@RequestStateMachine.state_class
class contactinglifeguard(Closable, Expirable, statemachine.State):
    "Contacting device's lifeguard server to reimage/reboot."

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 5

    def on_entry(self):
        if self.contact_lifeguard():
            self.machine.goto_state(pending)
            return
        counters = self.machine.read_counters()
        if counters.get(self.state_name, 0) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(devicenotfound)

    def on_timeout(self):
        self.machine.increment_counter(self.state_name)
        self.machine.goto_state(contactinglifeguard)

    def contact_lifeguard(self):
        device_request_data = {}
        request_config = data.request_config(self.machine.request_id)
        if request_config['boot_config']:
            event = 'please_pxe_boot' # TODO: state not specified yet
            device_request_data['boot_config'] = request_config['boot_config']
        else:
            event = 'please_power_cycle'

        device_url = 'http://%s/api/device/%s/event/%s/' % (
            data.get_server_for_request(self.machine.request_id),
            request_config['assigned_device'], event)
        try:
            urllib.urlopen(device_url, device_request_data)
        except IOError:
            logs.request_logs.add(self.machine.request_id,
                                  "could not contact lifeguard server at %s" %
                                  device_url)
            return False
        return True


@RequestStateMachine.state_class
class pending(Closable, Expirable, statemachine.State):
    "Request is pending while a device is located and prepared."

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 10

    def on_timeout(self):
        counter = self.machine.increment_counter(self.state_name)
        request_config = data.request_config(self.machine.request_id)
        device_state = data.device_status(request_config['device_name'])['state']
        if device_state == 'ready':
            self.machine.goto_state(self.ready)
        elif counter > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(devicenotfound)
        else:
            self.machine.goto_state(pending)


@RequestStateMachine.state_class
class devicenotfound(Closable, Expirable, statemachine.State):
    "No working unassigned device could be found."


@RequestStateMachine.state_class
class devicebusy(Closable, Expirable, statemachine.State):
    "The requested device is already assigned."


@RequestStateMachine.state_class
class ready(Closable, Expirable, statemachine.State):
    "Device has been prepared and is ready for use."


@RequestStateMachine.state_class
class expired(Closable, statemachine.State):
    "Request has expired."

    def on_entry(self):
        data.clear_device_request(self.machine.request_id)


@RequestStateMachine.state_class
class closed(statemachine.State):
    "Device was returned and request has been closed."

    def on_entry(self):
        data.clear_device_request(self.machine.request_id)
