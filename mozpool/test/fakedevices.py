# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import os
import time
import random
import logging
import threading
import requests
from mozpool import config, util
from mozpool.bmm import ping, sut
from mozpool.test import fakerelay

class Relay(fakerelay.Relay):

    def __init__(self, device, initial_status=1):
        super(Relay, self).__init__(initial_status)
        self.device = device

    def status_changed(self, new_status, device_on):
        self.device.set_power_status(device_on)


class PowerOff(Exception):
    pass


class Failure(Exception):
    pass


class Device(object):

    def __init__(self, rack, name, dev_dict):
        self.rack = rack
        self.db = rack.db
        self.name = name
        self.logger = logging.getLogger('fakedevices.%s' % name)

        # *our* notion of current state; this is mostly used to set timeouts
        # and for debugging purposes, as this class does not implement a state
        # machine.  Some of the states align with those in devicemachine.py,
        # for developer sanity
        self.state = 'unknown'

        # current power state (controlled by the corresponding Relay)
        self.power = True
        self.power_cond = threading.Condition()

        # the image on the sdcard
        self.sdcard_image = dev_dict['image']

        # current pingability status
        self.pingable = False

        # this is used in run() to figure out what to do first
        self.dev_dict = dev_dict

    # config parameters
    image_pingable = {
        'b2g': 0.97,
        'android': 0.99,
        # default: False
    }

    image_sut_functionality = {
        'b2g': {'sut_verify': 0.99, 'check_sdcard': 0.97},
        'android': {'sut_verify': 0.99, 'check_sdcard': 0.97},
    }

    # likelihoods of failure while waiting in each state
    failure_probability = {
        'booting': 0.05,
        'mobile_init_started': 0.01,
        'b2g_downloading': 0.05,
        'b2g_extracting': 0.08,
        'b2g_rebooting': 0.08,
        'running_b2g': 0.05
        # default: 0
    }

    def __str__(self):
        return " %s (%s)" % (self.name, self.state)

    def set_power_status(self, device_on):
        self.power = device_on
        with self.power_cond:
            self.power_cond.notify()

    def _wait(self, seconds=3600*24*365*10, splay=0):
        # first, randomly inject a failure
        p = self.failure_probability.get(self.state, 0)
        if p and random.random() < p:
            raise Failure

        # otherwise, calculate the time to wait, and wait.
        if splay:
            seconds = seconds + random.randint(-splay, splay)
        end = time.time() + seconds
        with self.power_cond:
            while time.time() < end:
                self.power_cond.wait(end - time.time())
                if not self.power:
                    raise PowerOff

    def _wait_for_power_on(self):
        with self.power_cond:
            while not self.power:
                self.power_cond.wait()

    def _set_state(self, state):
        self.logger.info('entering state %r' % state)
        self.state = state

    def _get_second_stage(self):
        mac_address = util.mac_with_dashes(
                self.db.devices.get_mac_address(self.name))
        dir = os.path.join(config.get('paths', 'tftp_root'), "pxelinux.cfg")
        filename = os.path.join(dir, "01-" + mac_address)
        if os.path.exists(filename):
            with open(filename) as f:
                cfg = f.read()
                mo = re.search('mobile-imaging-url=[^ ]*/([^ ]*).sh', cfg)
                if mo:
                    return mo.group(1)
                else:
                    self.logger.warn('PXE config does not contain a mobile-imaging-url; not PXE booting')
        # if nothing's found, return None
        return None

    def _send_event(self, event, set_state=True):
        # conveniently, most state and event names match
        if set_state:
            self._set_state(event)
        fqdn = config.get('server', 'fqdn')
        url = 'http://%s/api/device/%s/event/%s/' % (fqdn, self.name, event)
        requests.get(url)

    # patched methods from BMM

    def ping(self):
        ping_result = self.power and self.pingable
        if isinstance(self.pingable, float):
            ping_result = random.random() < self.pingable
        self.logger.debug('pinged; result=%s (state %s)' % (ping_result, self.state))
        return ping_result

    def sut_verify(self):
        prob_ok = self.image_sut_functionality.get(self.sdcard_image, {}).get('sut_verify')
        rv = False
        if prob_ok and random.random() < prob_ok:
            rv = True
        self.logger.debug('sut sut_verify: result=%s (state %s)' % (rv, self.state))
        return rv

    def check_sdcard(self):
        prob_ok = self.image_sut_functionality.get(self.sdcard_image, {}).get('check_sdcard')
        rv = False
        if prob_ok and random.random() < prob_ok:
            rv = True
        self.logger.debug('sut check_sdcard: result=%s (state %s)' % (rv, self.state))
        return rv

    def reboot(self):
        # if no SUT support, this won't work..
        if not self.image_sut_functionality.get(self.sdcard_image):
            rv = False

        # this works about 75% of the time, and is simulated internally as a power cycle
        elif random.random() < 0.75:
            self.set_power_status(False)
            time.sleep(2)
            self.set_power_status(True)
            rv = True
        else:
            time.sleep(3)
            rv = False
        self.logger.debug('sut reboot: result=%s (state %s)' % (rv, self.state))
        return rv

    # controller function

    def run(self):
        # handle startup specially, since the power is on, and the initial
        # state is determined from the DB.
        startup = True
        while True:
            try:
                if startup:
                    # start up in a failure state (not pingable and hung)
                    # unless the DB says this device is up and running, in
                    # which case boot it from its sdcard
                    startup = False
                    meth = self.fail
                    if self.dev_dict['state'] in ('free', 'ready'):
                        meth = self.boot_sdcard
                    meth()
                    continue

                # go through the boot process
                self._wait_for_power_on()
                self._set_state('booting')
                # load uboot, which makes us pingable for a bit
                self.pingable = True
                self._wait(7, splay=3)
                self.pingable = False

                second_stage = self._get_second_stage()
                if not second_stage:
                    self.boot_sdcard()
                else:
                    self.pingable = True
                    self._send_event('mobile_init_started')
                    self._wait(1)
                    meth = getattr(self, 'boot_%s' % second_stage.replace('-', '_'))
                    meth()
            except Failure:
                self.logger.warning('failure injected')
                self._set_state('failed')
            except PowerOff:
                self._set_state('off')
            except Exception, e:
                self.logger.error('exception from device emulator; powered off', exc_info=e)
                self._set_state('off')

    def boot_sdcard(self):
        self._set_state('running_%s' % self.sdcard_image)
        self.pingable = self.image_pingable.get(self.sdcard_image, False)

        # run forever..
        self._wait()

    def boot_b2g_second_stage(self):
        # get the boot_config and verify it
        fqdn = config.get('server', 'fqdn')
        url = 'http://%s/api/device/%s/bootconfig/' % (fqdn, self.name)
        r = requests.get(url)
        bootconfig = r.json()
        if 'b2gbase' not in bootconfig:
            self.logger('got invalid bootconfig - no b2gbase')
            raise Failure
        self.logger.debug('got b2gbase %r' % bootconfig['b2gbase'])

        self._send_event('b2g_downloading')
        self._wait(60, splay=30)
        self._send_event('b2g_extracting')
        self.sdcard_image = 'corrupt'
        self._wait(90, splay=60)
        self._send_event('b2g_rebooting')
        self._wait(3, splay=2) # time for the reboot command to do its thing
        self.pingable = False
        self.sdcard_image = 'b2g'
        self.boot_sdcard()

    def boot_android_second_stage(self):
        self._send_event('android_downloading')
        self.fail()
        self._wait(60, splay=30)
        self._send_event('android_extracting')
        self.sdcard_image = 'corrupt'
        self._wait(90, splay=60)
        self._send_event('android_rebooting')
        self._wait(3, splay=2) # time for the reboot command to do its thing
        self.pingable = False
        self.sdcard_image = 'android'
        self.boot_sdcard()

    def boot_maintenance_second_stage(self):
        self._send_event('maint_mode')
        # run for an hour, then crash
        self._wait(3600)
        self.fail()

    def boot_selftest_second_stage(self):
        self._send_event('self_test_running')
        if random.random() < 0.8:
            # run for a minute, then succeed
            self._wait(60)
            self._send_event('self_test_ok')
            self._wait()
        else:
            self.fail()

    def fail(self):
        self.pingable = False
        self._set_state('failed')
        self._wait()


class Chassis(object):

    def __init__(self, rack, relayboard_fqdn):
        self.rack = rack
        self.db = rack.db
        self.relayboard_fqdn = relayboard_fqdn
        host, port = relayboard_fqdn.split(':')
        self.relayboard = fakerelay.RelayBoard(relayboard_fqdn, ('', int(port)))
        self.devices = {}

    def __str__(self):
        return ("Chassis %s:\n" % self.relayboard_fqdn) + "\n".join(str(device) for device in self.devices.itervalues())

    def add_device(self, bank, relay, device):
        assert isinstance(bank, int)
        self.relayboard.add_relay(bank, relay,
                # set up the relay's initial power state based on the device
                Relay(device, initial_status=0 if device.power else 1))
        self.devices[device.name] = device

    def run(self):
        self.relayboard.run()


class Rack(object):
    """
    Represents a rack of chassis full of fake devices
    """

    def __init__(self, db):
        self.db = db

        # chassis are keyed by relay fqdn:port
        self.chassis = {}

        # devices are keyed by name and by fqdn
        self.devices = {}
        self.devices_by_fqdn = {}

        self.logger = logging.getLogger('fakedevices')
        self._patch()
        self._populate()

    def __str__(self):
        return "\n".join(str(chassis) for chassis in self.chassis.itervalues())

    def start(self):
        # each chassis gets a thread, and each device gets a thread
        for chassis in self.chassis.itervalues():
            thd = threading.Thread(name='chassis-%s' % chassis.relayboard_fqdn,
                                   target=chassis.run)
            thd.setDaemon(1)
            thd.start()

        for device in self.devices.itervalues():
            thd = threading.Thread(name='device-%s' % device.name,
                                   target=device.run)
            thd.setDaemon(1)
            thd.start()

    def _patch(self):
        # patch out bmm's ping and sut support so we can intercept checks of our own devices
        def patch(module, fn_name):
            old_fn = getattr(module, fn_name)
            def patched_fn(device_fqdn):
                if device_fqdn not in self.devices_by_fqdn:
                    return old_fn(device_fqdn)
                dev = self.devices_by_fqdn[device_fqdn]
                return getattr(dev, fn_name)()
            setattr(module, fn_name, patched_fn)
        patch(ping, 'ping')
        patch(sut, 'sut_verify')
        patch(sut, 'check_sdcard')
        patch(sut, 'reboot')

    def _populate(self):
        fqdn = config.get('server', 'fqdn')
        for dev_dict in self.db.devices.list(detail=True):
            # only emulate devices managed by this imaging sever
            if dev_dict['imaging_server'] != fqdn:
                continue

            # only emulate devices with relay info starting with 'localhost'
            hostname, bank, relay = dev_dict['relay_info'].rsplit(":", 2)
            if not hostname.startswith('localhost:'):
                continue

            if hostname not in self.chassis:
                self.chassis[hostname] = Chassis(self, hostname)
            chassis = self.chassis[hostname]

            device = Device(self, dev_dict['name'], dev_dict)
            self.devices[dev_dict['name']] = device
            self.devices_by_fqdn[dev_dict['fqdn']] = device
            chassis.add_device(int(bank[4:]), int(relay[5:]), device)

