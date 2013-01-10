#!/usr/bin/env python
# coding=utf-8

from setuptools import setup, find_packages

setup(name='mozpool',
      version='2.0.0',
      description='System to manage a pool of cranky mobile devices',
      author=u'Ted Mielczarek, Mark Côté, Dustin Mitchell',
      url='http://hg.mozilla.org/build/mozpool',
      author_email='ted@mielczarek.org',
      packages=find_packages('.'),
      package_data={
          'mozpool' : [ 'html/*.html', 'html/ui/*.html', 'html/ui/css/*.css', 'html/ui/js/*.js', 'html/ui/js/deps/*.js' ],
      },
      install_requires=[
          'sqlalchemy',
          'requests >= 1.0.0',
          'distribute',
          'argparse',
          'mozdevice',
          'templeton >= 0.6.2',
      ],
      entry_points={
          'console_scripts': [
              'pxe-config = mozpool.bmm.scripts:pxe_config_script',
              'relay = mozpool.bmm.scripts:relay_script',
              'mozpool-server = mozpool.web.server:main',
              'mozpool-inventorysync = mozpool.lifeguard.inventorysync:main',
              'mozpool-db = mozpool.db.scripts:db_script',
          ]
      }
)
