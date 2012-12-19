# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import threading
import time

def wait_for_async(start_fn):
    done_cond = threading.Condition()

    cb_result = []
    def cb(arg):
        cb_result.append(arg)
        done_cond.acquire()
        done_cond.notify()
        done_cond.release()

    done_cond.acquire()
    start_fn(cb)
    done_cond.wait()
    done_cond.release()

    return cb_result[0]

def run_async(callback_before, callback, operation, logger):
    def try_operation():
        res = False
        try:
            res = operation()
        except:
            logger.error("exception ignored in async operation:", exc_info=True)

        if callback_before is None or time.time() < callback_before:
            callback(res)
    threading.Thread(target=try_operation).start()
