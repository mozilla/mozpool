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
C{@YourStateMachine.state('statename')}.
"""

## in-memory locking

####
# Base and Mixins

class StateMachine(object):

    statesByName = {}

    # external interface

    def __init__(self, name, state_name):
        self.name = name
        self.state = self._make_state_instance(state_name)

    def handle_event(self, event):
        "Act on an event for this machine, specified by name"
        self.state.handle_event(event)

    def handle_timeout(self):
        "The current state for this machine has timed out"
        self.state.handle_timeout()

    # virtual methods

    def set_state(self, new_state, new_timeout_duration):
        raise NotImplementedError

    def get_counters(self):
        raise NotImplementedError

    def set_counters(self, counters):
        raise NotImplementedError

    # state mechanics

    def goto_state(self, new_state_name):
        """Transition the machine to a new state.  The caller should return
        immediately after calling this method."""
        self.state.on_exit()
        print "%s entering state %s" % (self.name, new_state_name) # TODO: mozlog
        self.state = self._make_state_instance(new_state_name)
        self.set_state(new_state_name, self.state._timeout_duration)
        self.state = self.state
        self.state.on_entry()

    def clear_counter(self, counter_name=None):
        """Clear a single counter or, if no counter is specified, all counters"""
        if counter_name:
            counters = self.get_counters()
            if counter_name in counters:
                del counters[counter_name]
                self.set_counters(counters)
        else:
            self.set_counters({})

    def increment_counter(self, counter_name):
        """Increment the value of the given counter, returning the new value."""
        counters = self.get_counters()
        counters[counter_name] = counters.get(counter_name, 0) + 1
        self.set_counters(counters)

    # decorators

    @classmethod
    def state(machine_class, name):
        """Decorator -- decorates a class as a state for a particular machine."""
        def wrap(state_class):
            state_class.name = name
            machine_class.statesByName[name] = state_class
            return state_class
        return wrap

    # utilities

    def _make_state_instance(self, state_name):
        state_cls = self.statesByName.get(state_name)
        if not state_cls:
            state_cls = self.statesByName['unknown']
        return state_cls(self)


class State(object):

    def __init__(self, machine):
        self.machine = machine

    def handle_event(self, event):
        self._event_methods[event](self)

    def handle_timeout(self):
        self._timeout_method()

    # hook methods

    def on_entry(self):
        "The board has just entered this state"
        pass

    def on_exit(self):
        "The board is about to leave this state"
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
    """Decorator -- designate this method to be called when the board is in this state for
    DURATION or more seconds"""
    def wrap(fn):
        fn.timeout_duration = duration
        return fn
    return wrap
