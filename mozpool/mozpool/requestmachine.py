# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import random
import requests
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

class RequestLogDBHandler(statedriver.DBHandler):

    object_name = 'request'
    log_object = logs.request_logs


class MozpoolDriver(statedriver.StateDriver):
    """
    The server code sets up an instance of this object as
    mozpool.mozpool.driver.
    """

    state_machine_cls = RequestStateMachine
    logger_name = 'request'
    thread_name = 'MozpoolDriver'
    log_db_handler = RequestLogDBHandler

    def __init__(self, poll_frequency=statedriver.POLL_FREQUENCY):
        statedriver.StateDriver.__init__(self, poll_frequency)
        self.imaging_server_id = data.find_imaging_server_id(
            config.get('server', 'fqdn'))

    def _get_timed_out_machine_names(self):
        return data.get_timed_out_requests(self.imaging_server_id)

    def poll_others(self):
        for request_id in data.get_expired_requests(self.imaging_server_id):
            self.handle_event(request_id, 'expire', None)


####
# Mixins

class Closable(object):

    def on_close(self, args):
        self.logger.info('Request closed.')
        self.machine.goto_state(closing)


class Expirable(object):

    def on_expire(self, args):
        self.logger.info('Request expired.')
        self.machine.goto_state(expired)


class ClearDeviceRequests(object):

    """
    Represents a second-to-final stage. We attempt to return the device
    to the 'free' state here.  If successful, or after permanent failure,
    we move to 'closed', which deletes the request-device association from
    the database.

    Note that the 'ready' state of the device state machine verifies that the
    device does indeed belong to a request and, if not, moves it back to 'free'.
    """

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 10

    def on_entry(self):
        if self.free_device():
            self.machine.goto_state(closed)
        else:
            count = self.machine.increment_counter(self.state_name)
            if count < self.PERMANENT_FAILURE_COUNT:
                self.logger.warn('Too many failed attempts to free device; '
                                 'just clearing request and giving up.')
                self.machine.goto_state(closed)

    def on_timeout(self):
        self.machine.goto_state(self.state_name)

    def free_device(self):
        assigned_device = data.get_assigned_device(self.machine.request_id)
        if assigned_device:
            device_url = 'http://%s/api/device/%s/event/free/' % (
                data.get_server_for_device(assigned_device), assigned_device)
            # FIXME: make this asynchronous so slow/missing servers don't halt
            # the state machine.
            try:
                requests.post(device_url)
            except (requests.ConnectionError, requests.Timeout,
                    requests.HTTPError):
                self.logger.warn('Could not contact lifeguard server at %s to '
                                 'free device.' % device_url)
                return False
        return True


@RequestStateMachine.state_class
class new(Closable, Expirable, statemachine.State):
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
    MAX_ANY_REQUESTS = 60
    MAX_SPECIFIC_REQUESTS = 1

    def on_entry(self):
        self.find_device()

    def on_timeout(self):
        self.machine.goto_state(finding_device)

    def find_device(self):
        self.logger.info('Finding device.')
        device_name = None
        count = self.machine.increment_counter(self.state_name)
        request = data.request_config(self.machine.request_id)
        image_is_reusable = data.image_is_reusable(request['image'])

        free_devices = data.get_free_devices(
                environment=request['environment'],
                device_name=request['requested_device'])

        if free_devices:
            if image_is_reusable:
                devices_with_image = [x for x in free_devices
                                      if x['image'] == request['image'] and
                                         data.from_json(x['boot_config']) ==
                                         data.from_json(request['boot_config'])]
                if devices_with_image:
                    free_devices = devices_with_image

            # pick a device at random from the returned list
            device_name = random.choice(free_devices)['name']
            self.logger.info('Assigning device %s.' % device_name)
            if data.reserve_device(self.machine.request_id,
                                                device_name):
                self.logger.info('Request succeeded.')
                self.machine.goto_state(contacting_lifeguard)
        else:
            self.logger.warn('Request failed!')
            if request['requested_device'] == 'any':
                if count >= self.MAX_ANY_REQUESTS:
                    self.logger.warn('Hit maximum number of attempts to find '
                                     'a free device; giving up.')
                    self.machine.goto_state(device_not_found)
            else:
                if count >= self.MAX_SPECIFIC_REQUESTS:
                    self.logger.warn('Requested device %s is busy.' %
                                     device_name)
                    self.machine.goto_state(device_busy)


@RequestStateMachine.state_class
class contacting_lifeguard(Closable, Expirable, statemachine.State):
    "Contacting device's lifeguard server to request reimage/reboot."

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 5

    def on_entry(self):
        request_config = data.request_config(self.machine.request_id)
        device_name = request_config['assigned_device']
        device_state = data.device_status(device_name)['state']
        if device_state != 'free':
            self.logger.error('Assigned device %s is in unexpected state %s '
                              'when about to contact lifeguard.' %
                              (device_name, device_state))
            self.machine.goto_state(device_busy)
            return

        if self.contact_lifeguard(request_config):
            self.machine.goto_state(pending)
            return
        counters = self.machine.read_counters()
        if counters.get(self.state_name, 0) > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(device_not_found)

    def on_timeout(self):
        self.machine.increment_counter(self.state_name)
        self.machine.goto_state(contacting_lifeguard)

    def contact_lifeguard(self, request_config):
        # If the requested image is reusable and we got a device with that
        # image and the requested bootconfig, just power cycle it.
        # Otherwise, image it.  Note that there will be a failure if the
        # image is not installed and the device is not imageable.
        event = ''
        device_request_data = {}
        assigned_device_name = request_config['assigned_device']

        if data.image_is_reusable(request_config['image']):
            device_config = data.device_config(request_config['assigned_device'])
            if (device_config['image'] == request_config['image'] and
                data.from_json(device_config['boot_config']) ==
                data.from_json(request_config['boot_config'])):
                event = 'please_power_cycle'

        if not event:
            # Use the device's hardware type and requested image to find the
            # pxe config, if any.
            event = 'please_image'
            device_request_data['boot_config'] = request_config['boot_config']
            device_request_data['image'] = request_config['image']

        device_url = 'http://%s/api/device/%s/event/%s/' % (
            data.get_server_for_device(assigned_device_name),
            assigned_device_name, event)

        # FIXME: make this asynchronous so slow/missing servers don't halt
        # the state machine.
        try:
            urllib.urlopen(device_url, json.dumps(device_request_data))
        except IOError:
            self.logger.warn('Could not contact lifeguard server at %s' %
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
            self.machine.goto_state(ready)
        elif counter > self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(device_not_found)
        else:
            self.machine.goto_state(pending)


@RequestStateMachine.state_class
class ready(Closable, Expirable, statemachine.State):
    "Device has been prepared and is ready for use."


@RequestStateMachine.state_class
class closing(ClearDeviceRequests, statemachine.State):
    "Request has received close event."


@RequestStateMachine.state_class
class expired(ClearDeviceRequests, statemachine.State):
    "Request has expired."


@RequestStateMachine.state_class
class device_not_found(ClearDeviceRequests, statemachine.State):
    "No working unassigned device could be found."


@RequestStateMachine.state_class
class device_busy(ClearDeviceRequests, statemachine.State):
    "The requested device is already assigned."


@RequestStateMachine.state_class
class closed(statemachine.State):
    "Device was returned and request has been closed."

    def on_entry(self):
        data.clear_device_request(self.machine.request_id)
