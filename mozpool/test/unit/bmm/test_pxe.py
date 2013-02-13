# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from mozpool import config
from mozpool.test.util import TestCase, DirMixin
from mozpool.bmm import pxe

class Tests(DirMixin, TestCase):

    def test_set_pxe(self):
        config.set('server', 'ipaddress', '1.2.3.4')
        cfg_dir = os.path.join(self.tempdir, 'tftp', 'pxelinux.cfg')
        cfg_filename = os.path.join(cfg_dir, '01-aa-bb-cc-dd-ee-ff')
        self.assertFalse(os.path.exists(cfg_dir))
        pxe.set_pxe('aabbccddeeff', 'IMG1 ip=%IPADDRESS%')
        self.assertEqual(open(cfg_filename).read(), 'IMG1 ip=1.2.3.4')

    def test_clear_pxe(self):
        cfg_dir = os.path.join(self.tempdir, 'tftp', 'pxelinux.cfg')
        cfg_filename = os.path.join(cfg_dir, '01-aa-bb-cc-dd-ee-ff')
        os.makedirs(cfg_dir)
        open(cfg_filename, "w").write("IMG2")
        pxe.clear_pxe('aabbccddeeff')
        self.assertFalse(os.path.exists(cfg_filename))

    def test_clear_pxe_nonexistent(self):
        # just has to not fail!
        pxe.clear_pxe('device1')
