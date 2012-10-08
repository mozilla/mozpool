#!/usr/bin/env python

from distutils.core import setup

setup(name='blackmobilemagic',
      version='1.0',
      description='Frontend for the BMM Boot and Imaging Service',
      author='Ted Mielczarek',
      author_email='tmielczarek@mozilla.com',
      packages=[ 'bmm' ],
      install_requires=[
          'web.py',
          # needs the git version for now; let's see if mcote can release 0.6 so we don't have to do this
          #'git+git://github.com/markrcote/templeton.git#egg=templeton'
      ],
     )
