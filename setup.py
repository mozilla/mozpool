#!/usr/bin/env python

from distutils.core import setup

setup(name='blackmobilemagic',
      version='0.1.0',
      description='Frontend for the BMM Boot and Imaging Service',
      author='Ted Mielczarek',
      author_email='ted@mielczarek.org',
      packages=[ 'bmm' ],
      install_requires=[
          'sqlalchemy',
          'requests',
          'web.py',
          # needs the git version for now; let's see if mcote can release 0.6 so we don't have to do this
          #'git+git://github.com/markrcote/templeton.git#egg=templeton'
      ],
      entry_points={
          'console_scripts': [
              'bmm-relay = bmm.relay:main',
              'bmm-server = bmm.server:main',
              'bmm-inventorysync = bmm.inventorysync:main',
          ]
      }
)
