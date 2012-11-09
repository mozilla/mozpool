# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""

This file implements an abstract, db-based state machine.

States are represented by subclasses of State.  This state is supplemented by a
finite number of counters, each ranging over a finite set of integers.  In
general, the behavior of the machine in a particular state is governed by the
State class; the counters are only used to fail out of cycles that might
otherwise cause hardware damage.

Transitions are triggered by events: timeouts, API calls, or internal events.

To use this module, subclass StateMachine and implement the virutal method,
then instantiate a number of state classes, decorated with
C{@YourStateMachine.state_class('statename')}.

This class implements process-local locking to prevent overlapping state
transitions.  Note that it is up to the caller to ensure that overlapping state
transitions do not occur in other processes.

"""

from __future__ import absolute_import
import logging
from mozpool import util

####
# Base and Mixins

class StateMachine(object):

    statesByName = {}
    locksByMachine = util.LocksByName()

    # external interface

    def __init__(self, machine_name):
        self.machine_name = machine_name
        self.state = None
        self.logger = logging.getLogger('statemachine.%s' % self.machine_name)

    def handle_event(self, event):
        "Act on an event for this machine, specified by name"
        self.lock()
        self.state = self._make_state_instance()
        try:
            self.state.handle_event(event)
        finally:
            self.state = None
            self.unlock()

    def handle_timeout(self):
        "The current state for this machine has timed out"
        self.lock()
        self.state = self._make_state_instance()
        try:
            self.state.handle_timeout()
        finally:
            self.state = None
            self.unlock()

    def conditional_goto_state(self, old_state, new_state, call_first=None):
        """
        Transition to NEW_STATE only if the device is in OLD_STATE.  Returns
        True on success, False on failure.  If CALL_FIRST is given, it is
        called with no arguments after the state change is guaranteed to go
        forward, but before it is actually performed.
        """
        self.lock()
        self.state = self._make_state_instance()
        try:
            if old_state != self.state.state_name:
                return False
            call_first()
            self.goto_state(new_state)
            return True
        finally:
            self.state = None
            self.unlock()

    # virtual methods

    def read_state(self):
        raise NotImplementedError

    def write_state(self, new_state, new_timeout_duration):
        raise NotImplementedError

    def read_counters(self):
        raise NotImplementedError

    def write_counters(self, counters):
        raise NotImplementedError

    # state mechanics

    def goto_state(self, new_state_name_or_class):
        """Transition the machine to a new state.  The caller should return
        immediately after calling this method."""
        if isinstance(new_state_name_or_class, type) and issubclass(new_state_name_or_class, State):
            new_state_name_or_class = new_state_name_or_class.state_name

        self.state.on_exit()

        self.logger.info('entering state %s' % (new_state_name_or_class,))

        self.state = self._make_state_instance(new_state_name_or_class)
        self.write_state(new_state_name_or_class, self.state._timeout_duration)

        self.state.on_entry()

    def clear_counter(self, counter_name=None):
        """Clear a single counter or, if no counter is specified, all counters"""
        assert self.state is not None, "state is not loaded"
        if counter_name:
            counters = self.read_counters()
            if counter_name in counters:
                del counters[counter_name]
                self.write_counters(counters)
        else:
            self.write_counters({})

    def increment_counter(self, counter_name):
        """Increment the value of the given counter, returning the new value."""
        assert self.state is not None, "state is not loaded"
        counters = self.read_counters()
        counters[counter_name] = counters.get(counter_name, 0) + 1
        self.write_counters(counters)
        return counters[counter_name]

    # decorator

    @classmethod
    def state_class(machine_class, state_class):
        """Decorator -- decorates a class as a state for a particular machine."""
        machine_class.statesByName[state_class.__name__] = state_class
        state_class.state_name = state_class.__name__
        return state_class

    # utilities

    def _make_state_instance(self, state_name=None):
        if not state_name:
            state_name = self.read_state()
        state_cls = self.statesByName.get(state_name)
        if not state_cls:
            state_cls = self.statesByName['unknown']
        return state_cls(self)

    def lock(self):
        """
        Lock this machine.  This should be used any time a state transition is processed.
        """
        self.locksByMachine.acquire(self.machine_name)

    def unlock(self):
        """
        Unlock this machine.  Call this after the state transition is complete.
        """
        self.locksByMachine.release(self.machine_name)


class State(object):

    def __init__(self, machine):
        self.machine = machine

    def handle_event(self, event):
        handler = self._event_methods.get(event)
        if handler:
            handler(self)
        else:
            self.machine.logger.warning("ignored event %s in state %s" % (event, self.__class__.__name__))

    def handle_timeout(self):
        self._timeout_method()

    # hook methods

    def on_entry(self):
        "The machine has just entered this state"
        pass

    def on_exit(self):
        "The machine is about to leave this state"
        pass

    # magic mechanics

    class __metaclass__(type):
        def __new__(meta, classname, bases, classDict):
            # extract the timeout method
            timeout_methods = [ m for m in classDict.itervalues()
                               if hasattr(m, 'timeout_duration') ]
            assert len(timeout_methods) <= 1
            if timeout_methods:
                classDict['_timeout_method'] = timeout_methods[0]
                classDict['_timeout_duration'] = timeout_methods[0].timeout_duration
            else:
                classDict['_timeout_method'] = None
                classDict['_timeout_duration'] = None

            # extract API event methods
            apiMethods = dict([ (m.event_name, m) for m in classDict.itervalues()
                           if hasattr(m, 'event_name') ])
            classDict['_event_methods'] = apiMethods

            cls = type.__new__(meta, classname, bases, classDict)
            return cls


def event_method(event):
    """Decorator -- designate this method to be called when the given API
    event is submitted"""
    def wrap(fn):
        fn.event_name = event
        return fn
    return wrap

def timeout_method(duration):
    """Decorator -- designate this method to be called when the machine is in this state for
    DURATION or more seconds"""
    def wrap(fn):
        fn.timeout_duration = duration
        return fn
    return wrap
