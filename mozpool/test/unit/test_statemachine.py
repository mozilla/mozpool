# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import mock
from mozpool import statemachine
from mozpool.test.util import TestCase

class StateMachineSubclass(statemachine.StateMachine):

    _counters = {}
    _state_name = 'state1'

    def read_state(self):
        return self._state_name

    def write_state(self, new_state, new_timeout_duration):
        self._state_name = new_state
        self._state_timeout_dur = new_timeout_duration

    def read_counters(self):
        return self._counters.copy()

    def write_counters(self, counters):
        self._counters = counters.copy()


@StateMachineSubclass.state_class
class state1(statemachine.State):

    TIMEOUT = 10

    called_on_poke = False
    called_on_timeout = False

    def on_poke(self, args):
        state1.called_on_poke = True

    def on_goto2(self, args):
        self.machine.goto_state('state2')

    def on_goto2_class(self, args):
        self.machine.goto_state(state2)

    def on_inc(self, args):
        self.machine.increment_counter('x')

    def on_clear(self, args):
        self.machine.clear_counter('x')

    def on_clear_all(self, args):
        self.machine.clear_counter()

    def on_timeout(self):
        state1.called_on_timeout = True


@StateMachineSubclass.state_class
class state2(statemachine.State):

    TIMEOUT = 20

    def on_timeout(self):
        pass

# test that different state machines can have states with the same names; this
# just introduces an extra state machine that ideally shouldn't interfere at
# all.
class Namespace: # so 'state1' doesn't get replaced in the module dict
    class StateMachineSubclass2(statemachine.StateMachine):
        pass
    @StateMachineSubclass2.state_class
    class state2(statemachine.State):
        pass


class Tests(TestCase):

    def setUp(self):
        self.db = mock.Mock(name='db')
        self.machine = StateMachineSubclass('test', 'machine', self.db)

    def test_event(self):
        state1.called_on_poke = False
        self.machine.handle_event('poke', {})
        self.assertTrue(state1.called_on_poke)

    def test_unknown_event(self):
        self.machine.handle_event('never-heard-of-it', {})

    def test_timeout(self):
        state1.called_on_timeout = False
        self.machine.handle_timeout()
        self.assertTrue(state1.called_on_timeout)

    def test_state_transition(self):
        # also tests on_exit and on_entry
        with mock.patch.object(state1, 'on_exit') as on_exit:
            with mock.patch.object(state2, 'on_entry') as on_entry:
                self.machine.handle_event('goto2', {})
                on_exit.assert_called()
                on_entry.assert_called()
        self.assertEqual(self.machine._state_name, 'state2')
        self.assertEqual(self.machine._state_timeout_dur, 20)

    def test_state_transition_class_name(self):
        self.machine.handle_event('goto2_class', {})
        self.assertEqual(self.machine._state_name, 'state2')
        self.assertEqual(self.machine._state_timeout_dur, 20)

    def test_increment_counter(self):
        self.machine.handle_event('inc', {})
        self.machine.handle_event('inc', {})
        self.assertEqual(self.machine._counters['x'], 2)

    def test_clear_counter_not_set(self):
        self.machine.handle_event('clear', {})
        self.assertFalse('x' in self.machine._counters)

    def test_clear_counter_set(self):
        self.machine._counters = dict(x=10)
        self.machine.handle_event('clear', {})
        self.assertFalse('x' in self.machine._counters)

    def test_clear_counter_all(self):
        self.machine._counters = dict(x=10, y=20)
        self.machine.handle_event('clear_all', {})
        self.assertEqual(self.machine._counters, {})
