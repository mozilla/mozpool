# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# This file implements the state machine for managing boards.  Each board has
# its own state machine.  States are represented by short strings (the class
# names below).  Each board also has "hidden state" in the form of a finite
# number of counters each ranging over a finite range of integers.  However,
# the behavior of each state is largely dictated by the visible name; the
# counters are only used to break what would otherwise be infinite state loops.
#
# Transitions are triggered by events: timeouts, API calls, or internal events.
#
# Instances of classes in the hierarchy here represent a particular board in a
# particular state.  When an event occurs for a board, the appropriate class is
# instantiated and the method corresponding to that event is invoked.
#
# See https://wiki.mozilla.org/ReleaseEngineering/BlackMobileMagic/State_Machine
# for more detail.

# TODO:
## status col -> 'state'
## add counters_json column, timeout_at column
## data methods: get_board_state, set_board_state
## in-memory locking

####
# Base and Mixins

class State(object):

    statesByName = {}

    # external interface

    @classmethod
    def create(cls, board):
        """Create a new State instance for the given board, specified by
        dictionary as returned from get_board_state."""
        state = board['state']
        state_cls = cls.statesByName.get(state, Unknown)
        return state_cls(board)

    def handle_api_event(self, event):
        "Act on an API event, specified by name"
        self._api_methods[event](self)

    def handle_timeout(self):
        "This board has timed out"
        self._timeout_method()

    # hook methods

    def on_entry(self):
        "The board has just entered this state"
        pass

    def on_exit(self):
        "The board is about to leave this state"
        pass

    # subclass utilities

    def goto_state(self, new_state):
        self.on_exit()
        self.board['state'] = new_state.name
        # TODO: update the db with the new state and timeout
        new_state = self.create(self.board)
        new_state.on_entry()
        return new_state # mostly for tests

    def clear_counter(self, counter_name=None):
        pass

    def increment_counter(self, counter_name):
        pass # note: returns new value

    def remove_symlink(self):
        pass

    def start_polling(self):
        pass

    def stop_polling(self):
        pass

    def start_power_cycle(self):
        pass

    def stop_power_cycle(self):
        pass

    # meta magic

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
            apiMethods = dict([ (m.api_event_name, m) for m in classDict.itervalues()
                           if hasattr(m, 'api_event_name') ])
            classDict['_api_methods'] = apiMethods

            # keep a list of all states by name
            cls = type.__new__(meta, classname, bases, classDict)
            if classname != 'State': # otherwise State isn't defined yet..
                State.statesByName[classname] = cls

            # and set the name attribute for easy use
            cls.name = classname
            return cls

    def __init__(self, board):
        self.board = board

    @staticmethod
    def api_event_method(event):
        """Decorator -- designate this method to be called when the given API
        event is submitted"""
        def wrap(fn):
            fn.api_event_name = event
            return fn
        return wrap

    @staticmethod
    def timeout_method(duration):
        """Decorator -- designate this method to be called when the board is in this state for
        DURATION or more seconds"""
        def wrap(fn):
            fn.timeout_duration = duration
            return fn
        return wrap


class AllowReboot(object):

    @State.api_event_method('rq-reboot')
    def on_rq_reboot(self):
        self.goto_state(RebootRebooting)


class AllowReimage(object):

    @State.api_event_method('rq-reimage')
    def on_rq_reimage(self):
        self.goto_state(ReimageRebooting)

        
class Failed(AllowReboot, AllowReimage, State):
    "Parent class for FailedXxx classes"

    def on_entry(self):
        # TODO: log the state
        pass


####
# Initial and steady states

class New(AllowReboot, AllowReimage, State):
    "This board is newly installed.  Await instructions."


class Unknown(AllowReboot, AllowReimage, State):
    "This board is in an unknown state.  Await instructions."


class Ready(AllowReboot, AllowReimage, State):
    "This board is production-ready."

    TIMEOUT = 300

    def on_entry(self):
        self.clear_counter()
        self.start_polling()

    def on_exit(self):
        self.stop_polling()

    @State.timeout_method(TIMEOUT)
    def on_timeout(self):
        self.goto_state(Ready)

    def on_poll_ok(self):
        # wait for the timeout to expire, rather than immediately re-polling
        pass

    def on_poll_failure(self):
        self.goto_state(RebootRebooting)


####
# Rebooting

class RebootRebooting(AllowReimage, State):
    "A reboot has been requested, and the board is being power-cycled."

    # wait for 60 seconds for a poer cycle to succeed, and do this a bunch of
    # times; failures here are likely a problem with the network or relay board,
    # so we want to retry until that's available.

    TIMEOUT = 60
    PERMANENT_FAILURE_COUNT = 200

    def on_entry(self):
        self.remove_symlink()
        self.start_power_cycle()

    def on_exit(self):
        self.stop_power_cycle()

    @State.timeout_method(TIMEOUT)
    def on_timeout(self):
        if self.increment_counter('RebootRebooting') > self.PERMANENT_FAILURE_COUNT:
            self.goto_state(FailedRebootRebooting)
        else:
            self.goto_state(RebootRebooting)

    def on_power_cycle_ok(self):
        self.clear_counter('RebootRebooting')
        self.goto_state(RebootComplete)

    def on_power_cycle_fail(self):
        pass # just wait for our timeout to expire


class RebootComplete(AllowReimage, State):
    "A reboot has been requested, and the power cycle is complete."

    # give the image ample time to come up and tell us that it's running, but if
    # that doesn't work after a few reboots, the image itself is probably bad
    TIMEOUT = 600
    PERMANENT_FAILURE_COUNT = 10

    @State.timeout_method(TIMEOUT)
    def on_timeout(self):
        if self.increment_counter('RebootComplete') > self.PERMANENT_FAILURE_COUNT:
            self.goto_state(FailedRebootComplete)
        else:
            self.goto_state(RebootRebooting)

    @State.api_event_method('image-running')
    def on_image_running(self):
        self.clear_counter('RebootComplete')
        self.goto_state(Ready)


class FailedRebootRebooting(Failed):
    "While rebooting, power-cycling the board has failed multiple times"


class FailedRebootComplete(Failed):
    "While rebooting, board has been power-cycled multiple times, but the image has not run."


####
# Reimaging

class ReimageRebooting(AllowReimage, State):
    "A reimage has been requested, and the board is being power-cycled."

    # TODO

