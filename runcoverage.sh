#! /bin/bash

set -e

coverage erase
coverage run --rcfile=.coveragerc runtests.py
coverage report
coverage html -i --rcfile=.coveragerc -d covhtml
