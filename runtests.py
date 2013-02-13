#!/usr/bin/env python
# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import os
import unittest
import logging

# subclasses to print test names to the log
class LoggingTextTestResult(unittest.TextTestResult):

    def startTest(self, test):
        logger.info("---- %s ----" % (self.getDescription(test),))
        super(LoggingTextTestResult, self).startTest(test)

class LoggingTextTestRunner(unittest.TextTestRunner):
    resultclass = LoggingTextTestResult

def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mozpool', 'test')
    suite.addTests(loader.discover(test_dir, 'test_*.py'))
    return suite

if __name__ == "__main__":
    open("test.log", "w") # truncate the file
    logging.basicConfig(level=logging.DEBUG, filename='test.log')
    logger = logging.getLogger('runtests')

    unittest.main(testRunner=LoggingTextTestRunner, buffer=True)
