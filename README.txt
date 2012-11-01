To run the server:

  bmm-server

optionally adding a port on the command line:

  bmm-server 8010


To install the DB schema (using the configured database):

  bmm-model


To flip relays:

  bmm-relay

and follow the command-line usage description


To synchronize the internal DB with inventory:

  bmm-inventorysync

(use --verbose to see what it's up to - note that it's not too fast)


Configuration should be based on the bmm/config.ini.dist template.  The config
can either be put in the `bmm/config.ini`, or anywhere else with $BMM_CONFIG
giving the full path.


To run the tests:

 * install mock
 * install paste
 * run `python runtests.py`
