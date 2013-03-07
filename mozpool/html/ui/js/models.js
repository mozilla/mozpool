/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

//
// db-backed models
//

var UpdateableCollection = Backbone.Collection.extend({
    refreshInterval: 30000,
    // controls parsing the result of the fetch
    responseAttr: '',  // expect data at this key in the response
    namesOnly: false, // if true, the response is a list of names
    // whether to add, remove, or update collection items when
    // merging new data
    addWhenMerging: true,
    removeWhenMerging: true,
    updateWhenMerging: true,
    // ids that should always be in the model

    initialize: function (args) {
        _.bindAll(this, 'update', 'parse');

        // keep track of whether we're updating *now*, and whether an update
        // has been requested.  The timeoutId is the window.setTimeout
        // identifier for the periodic updates.  callWhenUpdated keeps a list
        // of functions to call when the current update is complete.
        this.updating = false;
        this.updateRequested = false;
        this.timeoutId = null;
        this.callWhenUpdated = [];
    },

    mungeResponse: function(response) {
        return response;
    },

    parse: function(response) {
        var self = this;

        response = this.mungeResponse(response)[this.responseAttr];
        if (this.namesOnly) {
            // add id columns, based on the names
            response = $.map(response, function(name) { return { name: name, id: name }; });
        }

        var old_ids = self.map(function(b) { return b.get('id'); });
        var new_ids = _.map(response, function (b) { return b.id; });

        // calculate added and removed elements from differences
        if (self.removeWhenMerging) {
            _.each(_.difference(old_ids, new_ids), function (id) {
                self.remove(self.get(id));
            });
        }

        if (self.addWhenMerging) {
            _.each(_.difference(new_ids, old_ids), function (id) {
                var attrs = response[_.indexOf(new_ids, id)];
                self.push(new self.model(attrs), {'sort': false});
            });
        }

        // then any updates to the individual models that haven't been added or
        // removed
        if (self.updateWhenMerging) {
            _.each(_.intersection(new_ids, old_ids), function (id) {
                var attrs = response[_.indexOf(new_ids, id)];
                var model = self.get(id);
                model.set(attrs);
            });
        }

        // sort, since we added things without sorting.
        if (self.comparator) {
            self.sort();
        }

        // this just instructs the fetch/add to not anything else:
        return [];
    },

    // request that the collection be updated soon.
    update: function(next) {
        this.updateRequested = true;
        if (!this.updating) {
            this._startUpdate();
        }
        if (next) {
            this.callWhenUpdated.push(next);
        }
    },

    _startUpdate: function() {
        var self = this;

        if (this.timeoutId) {
            window.clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }
        this.updating = true;
        this.updateRequested = false;

        this.fetch({
            add: true,
            success: function() {
                var calls = self.callWhenUpdated;
                self.callWhenUpdated = [];
                _.each(calls, function(c) { c(); });

                self.updating = false;
                if (self.updateRequested) {
                    self._startUpdate();
                } else {
                    // schedule to update again after refreshInterval
                    self.timeoutId = window.setTimeout(self.update, self.refreshInterval);
                }
            },
            error: function(jqxhr, response) {
                show_error('AJAX Error while fetching ' + name + ': ' + response.statusText);
                // this error is pretty much terminal...
            }
        });
    }
});

var Device = Backbone.Model.extend({
    // in addition to all of the attributes from the REST API, this has a
    // 'selected' attribute that is local to the client
    initialize: function(args) {
        this.set('selected', false);
    }
});

var Devices = UpdateableCollection.extend({
    url: '/api/device/list/?details=true',
    model: Device,
    responseAttr: 'devices',

    comparator: function(line) {
        return line.get('name');
    }
});

var DeviceNames = UpdateableCollection.extend({
    // only sets the 'id' attribute of the Device model to the device name
    url: '/api/device/list/',
    model: Device,
    responseAttr: 'devices',
    namesOnly: true,
    updateWhenMerging: false // no need, since they're just names
});

var Environment = Backbone.Model.extend({
});

var Environments = UpdateableCollection.extend({
    url: '/api/environment/list/',
    model: Environment,
    responseAttr: 'environments',
    namesOnly: true,
    updateWhenMerging: false, // no need, since they're just names
});

var Request = Backbone.Model.extend({
    initialize: function(args) {
        this.set('selected', false);
    }
});

var Requests = UpdateableCollection.extend({
    url: function() {
        return '/api/request/list/' + (this.includeClosed ? '?include_closed=1'
                                                          : '');
    },
    model: Request,
    responseAttr: 'requests',
    includeClosed: false
});

var PxeConfig = Backbone.Model.extend({
});

var PxeConfigs = UpdateableCollection.extend({
    url: '/api/bmm/pxe_config/list/?active_only=1',
    model: PxeConfig,
    responseAttr: 'pxe_configs',
    namesOnly: true
});

var Image = Backbone.Model.extend({
});

var Images = UpdateableCollection.extend({
    url: '/api/image/list/',
    model: Image,
    responseAttr: 'images',
    namesOnly: false,
    mungeResponse: function(response) {
        // use the names as id's
        _.each(response['images'], function(img) {
            img['id'] = img['name'];
        });
        return response;
    },
});

var LogLine = Backbone.Model.extend({
});

var Log = UpdateableCollection.extend({
    model: LogLine,
    refreshInterval: 5000, // 5s, so we don't crush the DB
    url: null, // filled in by setupUrl
    doneInitialFetch: false,
    responseAttr: 'log',

    setupUrl: function(base, limit) {
        this.baseUrl = base;
        this.url = base + '?limit=' + limit;
    },

    fetch: function(args) {
        var rv = UpdateableCollection.prototype.fetch.call(this, args);
        // update the URL if we've done the initial fetch
        if (!this.doneInitialFetch) {
            this.doneInitialFetch = true;
            // only fetch the last five minutes from here on out, to make merging easier.
            // This lets us miss our refreshInterval by quite a bit, but not forever (TODO)
            this.url = this.baseUrl + '?timeperiod=300';
        }
        return rv;
    },

    comparator: function(line) {
        return line.get('id');
    }
});

//
// client-side control state
//

var CurrentControlState = Backbone.Model.extend({
    // current values for all of the onscreen controls
    initialize: function (args) {
        this.set('device', 'any');
        this.set('environment', '');
        this.set('assignee', '');
        this.set('request_duration', '3600');
        this.set('renew_duration', '3600');
        this.set('new_state', '');
        this.set('pxe_config', '');
        this.set('boot_config_raw', '');
        this.set('b2gbase', '');
        this.set('please_verb', '');
        this.set('image', 'b2g');
        this.set('set_comments', false);
        this.set('comments', '');
    }
});

//
// Static Data
//

var PleaseVerb = Backbone.Model.extend({
});

var PleaseVerbs = Backbone.Collection.extend({
    model: PleaseVerb,

    initialize: function(args) {
        // fill with static values
        this.push({name: 'please_image', id: 'please_image', needs_image: true});
        this.push({name: 'please_power_cycle', id: 'please_power_cycle', needs_image: false});
        this.push({name: 'please_self_test', id: 'please_self_test', needs_image: false});
        this.push({name: 'please_start_maintenance', id: 'please_start_maintenance', needs_image: false});
    }
});


//
// Jobs
//

var DeviceJob = Backbone.Model.extend({
    initialize: function (args) {
        this.device = args.model;
        this.set('device', this.device);
        this.set('job_type', args.job_type);
        this.set('job_args', args.job_args);
        this.set('device_name', this.device.get('name'));
    },

    job_subject: function() {
        return 'device ' + this.get('device_name');
    }
});

var RequestJob = Backbone.Model.extend({
    initialize: function (args) {
        this.request = args.model;
        this.set('request', this.request);
        this.set('job_type', args.job_type);
        this.set('job_args', args.job_args);
        this.set('request_id', this.request ? this.request.get('id') : 0);
    },

    job_subject: function() {
        return 'request ' + this.get('request_id');
    }
});

var JobQueue = Backbone.Collection.extend({
    model: null,  // override after creation
});
