# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import random

from mozpool import config, statemachine, statedriver, util, async, mozpool

####
# State machine

# FIXME: Very similar to DeviceStateMachine; refactor.

class RequestStateMachine(statemachine.StateMachine):

    def __init__(self, request_id, db):
        statemachine.StateMachine.__init__(self, 'request', request_id, db)
        self.request_id = request_id

    def read_state(self):
        return self.db.requests.get_machine_state(self.request_id)

    def write_state(self, new_state, timeout_duration):
        if timeout_duration:
            state_timeout = (datetime.datetime.now() +
                             datetime.timedelta(seconds=timeout_duration))
        else:
            state_timeout = None
        self.db.requests.set_machine_state(self.request_id,
                                           new_state, state_timeout)

    def read_counters(self):
        return self.db.requests.get_counters(self.request_id)

    def write_counters(self, counters):
        self.db.requests.set_counters(self.request_id, counters)


####
# Driver

class RequestLogDBHandler(statedriver.DBHandler):

    object_type = 'request'


class MozpoolDriver(statedriver.StateDriver):
    """
    The server code sets up an instance of this object as
    mozpool.mozpool.driver.
    """

    state_machine_cls = RequestStateMachine
    logger_name = 'request'
    thread_name = 'MozpoolDriver'
    log_db_handler = RequestLogDBHandler

    def __init__(self, db, poll_frequency=statedriver.POLL_FREQUENCY):
        statedriver.StateDriver.__init__(self, db, poll_frequency)
        self._imaging_server_id = None

    def _get_timed_out_machine_names(self):
        return self.db.requests.list_timed_out(self.imaging_server_id)

    def poll_others(self):
        for request_id in self.db.requests.list_expired(self.imaging_server_id):
            self.handle_event(request_id, 'expire', None)

    @property
    def imaging_server_id(self):
        if self._imaging_server_id is None:
            self._imaging_server_id = self.db.imaging_servers.get_id(config.get('server', 'fqdn'))
        return self._imaging_server_id

####
# Mixins

class Closable(object):

    def on_close(self, args):
        self.logger.info('Request closed.')
        self.machine.goto_state(closed)

    def on_expire(self, args):
        self.logger.info('Request expired.')
        self.machine.goto_state(closed)


class ClearDeviceRequests(object):
    """
    Clear the device_request.  This is mixed into every "terminal" state.
    """

    def on_entry(self):
        self.db.device_requests.clear(self.machine.request_id)


@RequestStateMachine.state_class
class new(Closable, statemachine.State):
    "New request; no action taken yet."

    def on_find_device(self, args):
        self.machine.goto_state(finding_device)


@RequestStateMachine.state_class
class finding_device(Closable, statemachine.State):
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
    MAX_SPECIFIC_REQUESTS = 2

    def on_entry(self):
        self.find_device()

    def on_timeout(self):
        self.machine.goto_state(finding_device)

    def find_device(self):
        self.logger.info('Finding device.')
        device_name = None
        count = self.machine.increment_counter(self.state_name)
        self.db.device_requests.clear(self.machine.request_id)
        request = self.db.requests.get_info(self.machine.request_id)
        image_is_reusable = self.db.images.is_reusable(request['image'])

        avail_devices = self.db.devices.list_available(
                environment=request['environment'],
                device_name=request['requested_device'])

        if avail_devices:
            if image_is_reusable:
                devices_with_image = [x for x in avail_devices
                                      if x['image'] == request['image'] and
                                         util.from_json(x['boot_config']) ==
                                         util.from_json(request['boot_config'])]
                if devices_with_image:
                    avail_devices = devices_with_image

            # pick a device at random from the returned list
            device_name = random.choice(avail_devices)['name']
            self.logger.info('Assigning device %s.' % device_name)
            if self.db.device_requests.add(self.machine.request_id,
                                                device_name):
                self.logger.info('Request succeeded.')
                self.machine.goto_state(contact_lifeguard)
        else:
            self.logger.warn('Request failed!')
            if request['requested_device'] == 'any':
                if count >= self.MAX_ANY_REQUESTS:
                    self.logger.warn('Hit maximum number of attempts to find '
                                     'a free device; giving up.')
                    self.machine.goto_state(failed_device_not_found)
            else:
                if count >= self.MAX_SPECIFIC_REQUESTS:
                    self.logger.warn('Requested device %s is busy.' %
                                     request['requested_device'])
                    self.machine.goto_state(failed_device_busy)
                    return
                # check the device status - if it's failed, then short-circuit
                # to failed_bad_device
                state = self.db.devices.get_machine_state(request['requested_device'])
                if state.startswith('failed_'):
                    self.machine.goto_state(failed_bad_device)


@RequestStateMachine.state_class
class contact_lifeguard(Closable, statemachine.State):
    """About to contact lifeguard, after a timeout.  This allows find_device to
    return before beginning to contact lifeguard, which can take a while when
    the DB is slow."""

    TIMEOUT = 0

    def on_timeout(self):
        self.machine.goto_state(contacting_lifeguard)


@RequestStateMachine.state_class
class contacting_lifeguard(Closable, statemachine.State):
    "Contacting device's lifeguard server to request reimage/reboot."

    TIMEOUT = 30
    PERMANENT_FAILURE_COUNT = 5

    def on_entry(self):
        req = self.db.requests.get_info(self.machine.request_id)
        device_name = req['assigned_device']
        device_state = self.db.devices.get_machine_state(device_name)
        if device_state != 'ready':
            self.logger.error('Assigned device %s is in unexpected state %s '
                              'when about to contact lifeguard.' %
                              (device_name, device_state))
            self.machine.goto_state(finding_device)
            # note that there's still a small chance of a race here between
            # mozpool and lifeguard: lifeguard begins self-testing the device
            # after this check and before it receives the event below; the
            # device eventually returns to the 'ready' state, but has not sent
            # the request.  The timeout for 'pending' will catch this rare
            # situation.
            return

        # If the requested image is reusable and we got a device with that
        # image and the requested bootconfig, just power cycle it.
        # Otherwise, image it.  Note that there will be a failure if the
        # image is not installed and the device is not imageable.
        event = ''
        device_request_data = {}
        assigned_device_name = req['assigned_device']

        if self.db.images.is_reusable(req['image']):
            dev = self.db.devices.get_image(req['assigned_device'])
            if (dev['image'] == req['image'] and
                util.from_json(dev['boot_config']) ==
                util.from_json(req['boot_config'])):
                event = 'please_power_cycle'

        if not event:
            # Use the device's hardware type and requested image to find the
            # pxe config, if any.
            event = 'please_image'
            device_request_data['boot_config'] = req['boot_config']
            device_request_data['image'] = req['image']

        # try to ask lifeguard to start imaging or power cycling
        device_url = 'http://%s/api/device/%s/event/%s/' % (
            self.db.devices.get_imaging_server(assigned_device_name),
            assigned_device_name, event)
        def posted(result):
            if result.status_code != 200:
                self.logger.warn("got %d from Lifeguard" % result.status_code)
                return
            mozpool.driver.handle_event(self.machine.request_id, 'lifeguard_contacted', {})
        async.requests.post.start(posted, device_url,
                data=json.dumps(device_request_data))

    def on_lifeguard_contacted(self, args):
        self.machine.goto_state(pending)

    def on_timeout(self):
        if self.machine.increment_counter(self.state_name) >= self.PERMANENT_FAILURE_COUNT:
            self.machine.clear_counter(self.state_name)
            self.machine.goto_state(failed_device_not_found)
        else:
            self.machine.goto_state(contacting_lifeguard)



@RequestStateMachine.state_class
class pending(Closable, statemachine.State):
    "Request is pending while a device is located and prepared."

    # This is used as a polling interval, in case we miss a notification from
    # lifeguard that the operation is finished.
    TIMEOUT = 60

    # wait a total of 20m for the device to be prepared, but only if the
    # request is not for a specific device; see on_timeout, below.  This is
    # only to account for e.g., a lifeguard failure.  If the device fails but
    # lifeguard is still OK, then lifeguard will tell us with an imaging
    # result.
    PERMANENT_FAILURE_COUNT = 20

    # retry bad images this many times, just to be sure
    BAD_IMAGE_FAILURE_COUNT = 2

    def on_timeout(self):
        # poll first, and if that works, nothing more to do
        if self.check_imaging_result():
            return

        # if this request is for a specific device, then keep waiting until the request
        request = self.db.requests.get_info(self.machine.request_id)
        if request['requested_device'] != 'any':
            self.machine.goto_state(pending)
            return

        # otherwise, wait until PERMANENT_FAILURE_COUNT, and then assume that something has
        # failed in lifeguard (e.g., imaging server failure)
        if self.machine.increment_counter(self.state_name) < self.PERMANENT_FAILURE_COUNT:
            self.machine.goto_state(pending)
        else:
            self.machine.goto_state(finding_device)

    def on_lifeguard_finished(self, args):
        imaging_result = args.get('imaging_result')
        self.check_imaging_result(imaging_result)

    def check_imaging_result(self, imaging_result=None):
        if not imaging_result:
            imaging_result = self.db.device_requests.get_result(self.machine.request_id)
        if not imaging_result:
            # no result yet
            return False
        # the remaining result strings form a tiny little code shared with lifeguard
        elif imaging_result == 'complete':
            self.machine.goto_state(ready)
        elif imaging_result == 'failed-bad-image':
            # if the image was responsible for the failure, and we've
            # exceeded the allowable bad images, give up
            if self.machine.increment_counter('bad-images') < self.BAD_IMAGE_FAILURE_COUNT:
                self.machine.goto_state(finding_device)
            else:
                self.machine.goto_state(failed_bad_image)
        elif imaging_result == 'failed-bad-device':
            request = self.db.requests.get_info(self.machine.request_id)
            if request['requested_device'] == 'any':
                # try another device if possible
                self.machine.goto_state(finding_device)
            else:
                # otherwise indicate that this device is bad
                self.machine.goto_state(failed_bad_device)
        else:
            self.logger.warn('unknown imaging result %s' % imaging_result)
            self.machine.goto_state(finding_device)
        return True


@RequestStateMachine.state_class
class ready(Closable, statemachine.State):
    "Device has been prepared and is ready for use."


@RequestStateMachine.state_class
class failed_device_not_found(ClearDeviceRequests, statemachine.State):
    "No working unassigned device could be found."


@RequestStateMachine.state_class
class failed_bad_image(ClearDeviceRequests, statemachine.State):
    "Installing the image on the device failed in such a way that it is likely a bad image."


@RequestStateMachine.state_class
class failed_bad_device(ClearDeviceRequests, statemachine.State):
    "The requested device has failed."


@RequestStateMachine.state_class
class failed_device_busy(ClearDeviceRequests, statemachine.State):
    "The requested device is already assigned."


@RequestStateMachine.state_class
class expired(ClearDeviceRequests, Closable, statemachine.State):
    # kept here for migration from Mozpool-3.0.1; expired requests will be closed.
    "Request has expired."


@RequestStateMachine.state_class
class closed(ClearDeviceRequests, statemachine.State):
    "Device was returned and request has been closed."
