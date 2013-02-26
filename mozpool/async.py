# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import threading
import time
import requests as requests_mod

logger = logging.getLogger('async')

class TimeoutError(Exception):
    pass

class AsyncOperation(object):
    """
    Abstract base class for operations that occur asynchronously, on another
    thread, in a finite duration.
    """
    __slots__ = ['obj', 'func', 'max_time']

    def __init__(self, obj, func, max_time):
        self.obj = obj
        self.func = func
        self.max_time = max_time

    def start(self, callback, *args, **kwargs):
        """
        Start an asynchronous invocation.  The given callback will be invoked
        before `max_time` seconds have elapsed, or not invoked at all.

        The callback should take one argument, which will be the result of the
        operation.  If the operation raises an exception, that exception will
        be logged, but the callback will not be invoked.  Try to avoid that.

        This method will never block.
        """
        callback_before = time.time() + self.max_time
        def try_operation():
            res = False
            try:
                res = self.func(self.obj, *args, **kwargs)
            except:
                logger.error("exception ignored in async operation:", exc_info=True)
                return

            if time.time() < callback_before:
                callback(res)
        threading.Thread(target=try_operation).start()

    def run(self, *args, **kwargs):
        """
        Run the asynchronous operation synchronously.

        This will return the result of the operation, or raise `TimeoutError`
        after `max_time` seconds, if the operation is not yet complete.

        The advantage of this method over simply invoking the operation is that
        it is guaranteed to finish in `max_time` seconds, regardless of the
        behavior of the operation.
        """
        done_cond = threading.Condition()

        cb_result = []
        def cb(arg):
            cb_result.append(arg)
            with done_cond:
                done_cond.notify()

        with done_cond:
            self.start(cb, *args, **kwargs)
            done_cond.wait(self.max_time)

        if not cb_result:
            raise TimeoutError
        return cb_result[0]


def async_operation(max_time):
    """Create an asynchronous operation out of the decorated method.  This will
    not work for plain (non-method) functions."""
    def wrap(func):
        # use a property to get 'self' for the wrapped method
        return property(fget=lambda obj : AsyncOperation(obj, func, max_time))
    return wrap

class AsyncRequests(object):
    """
    An async wrapper for requests.get and requests.post.

    Note that exceptions are not propagated asynchronously; any requests errors
    will be logged, but the callback will simply not occur.  All operations
    have a hard-coded 30-second timeout.

    An instance of this object is available at mozpool.async.requests
    """

    @async_operation(30)
    def get(self, url, **kwargs):
        return requests_mod.get(url, timeout=30, **kwargs)

    @async_operation(30)
    def post(self, url, data=None, **kwargs):
        return requests_mod.post(url, data=data, timeout=30, **kwargs)

requests = AsyncRequests()
