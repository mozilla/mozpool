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
        logs.request_logs.add(self.machine.request_id, "request closed")
        self.machine.goto_state(closing)


class Expirable(object):

    def on_expire(self, args):
        logs.request_logs.add(self.machine.request_id, "request expired")
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
                logs.request_logs.add(
                    self.machine.request_id,
                    "too many failed attempts; just clearing request "
                    "and giving up")
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
                logs.request_logs.add(
                    self.machine.request_id,
                    "could not contact lifeguard server at %s to free device" %
                    device_url)
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
        # FIXME: refactor.
        device_name = None
        count = self.machine.increment_counter(self.state_name)
        request = data.dump_requests(self.machine.request_id)[0]
        if request['requested_device'] == 'any':
            free_devices = data.get_free_devices()
            random.shuffle(free_devices)
        else:
            free_devices = [request['requested_device']]
        for device_name in free_devices:
            # check against environment
            env = request['environment']
            if env != 'any' and data.device_environment(device_name) != env:
                self.logger.info('%s does not match env %s' % (device_name, env))
                continue
            break
        else:
            self.logger.info('no free devices matching requirements')
            return

        self.logger.info('assigning device %s' % (device_name,))
        if device_name and data.reserve_device(self.machine.request_id,
                                               device_name):
            self.logger.info('request succeeded')
            self.machine.goto_state(contacting_lifeguard)
        else:
            self.logger.warn('request failed!')
            if request['requested_device'] == 'any':
                if count >= self.MAX_ANY_REQUESTS:
                    logs.request_logs.add(
                        self.machine.request_id,
                        'hit maximum number of attempts; giving up')
                    self.machine.goto_state(device_not_found)
            else:
                if count >= self.MAX_SPECIFIC_REQUESTS:
                    logs.request_logs.add(
                        self.machine.request_id,
                        'requested device %s is busy' % device_name)
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
            logs.request_logs.add(
                self.machine.request_id,
                'assigned device %s is in unexpected state %s when about '
                'to contact lifeguard.' % (device_name, device_state))
            self.machine.goto_state(device_busy)
            return

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

        # Determine if we are imaging or just rebooting.
        # We need to pass boot_config as a JSON string, but verify that it's
        # a non-null object.
        if json.loads(request_config['boot_config']):
            event = 'please_pxe_boot'
            device_request_data['boot_config'] = request_config['boot_config']
            # FIXME: differentiate between b2g builds and other (future) image
            # types.
            device_request_data['pxe_config'] = config.get('mozpool',
                                                           'b2g_pxe_config')
        else:
            event = 'please_power_cycle'

        device_url = 'http://%s/api/device/%s/event/%s/' % (
            data.get_server_for_device(request_config['assigned_device']),
            request_config['assigned_device'], event)

        # FIXME: make this asynchronous so slow/missing servers don't halt
        # the state machine.
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
    "Device has been prepared and is ready for use."


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
