#!/usr/bin/env python

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
              'board-powercycle = mozpool.bmm.scripts:board_power',
              'mozpool-server = mozpool.web.server:main',
              'mozpool-inventorysync = mozpool.lifeguard.inventorysync:main',
              'mozpool-model = mozpool.db.scripts:mozpool_model',
          ]
      }
)
