#!/usr/bin/env python

from setuptools import setup

setup(name='blackmobilemagic',
      version='0.2.1',
      description='Frontend for the BMM Boot and Imaging Service',
      author='Ted Mielczarek',
      author_email='ted@mielczarek.org',
      packages=[ 'bmm' ],
      package_data={
          'bmm': [ 'html/*.html', 'html/css/*.css', 'html/js/*.js', 'html/js/deps/*.js' ],
      },
      install_requires=[
          'sqlalchemy',
          'requests',
          'templeton'
      ],
      entry_points={
          'console_scripts': [
              'bmm-relay = bmm.relay:main',
              'bmm-server = bmm.server:main',
              'bmm-inventorysync = bmm.inventorysync:main',
              'bmm-model = bmm.data:bmm_model',
          ]
      }
)
