# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import sqlalchemy as sa
from mozpool import config
from mozpool.db import scripts
from mozpool.test.util import ScriptMixin, ConfigMixin, DirMixin, TestCase

# set by the script in test_run
conn = None

class Tests(ScriptMixin, DirMixin, ConfigMixin, TestCase):

    def setUp(self):
        super(Tests, self).setUp()
        self.db_url = 'sqlite:///%s/tmp.sqlite' % self.tempdir
        config.set('database', 'engine', self.db_url)

    def test_usage(self):
        self.assertEqual(self.run_script(scripts.db_script,
            [ ]),
            1)
        self.assertEqual(self.run_script(scripts.db_script,
            [ 'whutnow' ]),
            1)

    def test_create_schema(self):
        self.assertEqual(self.run_script(scripts.db_script,
            [ 'create-schema' ]),
            0)
        engine = sa.create_engine(self.db_url)
        # just make sure the devices table exists..
        engine.execute("select * from devices")

    def test_run(self):
        script_fn = os.path.join(self.tempdir, "scpt.py")
        # reference local var 'conn' then touch a file
        script = "conn.execute; open('%s-out', 'w')" % script_fn
        open(script_fn, "w").write(script)

        self.assertEqual(self.run_script(scripts.db_script,
            [ 'run', script_fn ]),
            0)
        self.assertTrue(os.path.exists('%s-out' % script_fn))
