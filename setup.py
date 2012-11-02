#!/usr/bin/env python
# coding=utf-8

from setuptools import setup

setup(name='mozpool',
      version='0.3.0',
      description='System to manage a pool of cranky mobile devices',
      author=u'Ted Mielczarek, Mark Côté, Dustin Mitchell',
      author_email='ted@mielczarek.org',
      packages=[ 'mozpool' ],
      package_data={
          'mozpool': [ 'html/*.html', 'html/css/*.css', 'html/js/*.js', 'html/js/deps/*.js' ],
      },
      install_requires=[
          'sqlalchemy',
          'requests',
          'templeton'
      ],
      entry_points={
          'console_scripts': [
              'relay = mozpool.bmm.scripts:relay_script',
              'mozpool-server = mozpool.web.server:main',
              'mozpool-inventorysync = mozpool.lifeguard.inventorysync:main',
              'mozpool-db = mozpool.db.scripts:db_script',
          ]
      }
)
