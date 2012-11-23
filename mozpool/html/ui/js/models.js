/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// NOTE: all top-level models appear as attributes of window, using the
// lower-cased name.  So the Devices instance is window.devices.

// db-backed models

var UpdateableCollection = Backbone.Collection.extend({
    responseAttr: '',  // override
    refreshInterval: 30000,

    initialize: function (args) {
        _.bindAll(this, 'update', 'parse');

        // objects automatically update themselves; set up to update
        // TODO: this could be done better with fetch({merge:true}), but that's
        // not in backbone-0.9.2
        window.setTimeout(this.update, this.refreshInterval);
    },

    parse: function(response) {
        var self = this;
        var old_ids = self.map(function(b) { return b.get('id'); });
        var new_ids = _.map(response[self.responseAttr],
                            function (b) { return b.id; });

        // calculate added and removed elements from differences
        _.each(_.difference(old_ids, new_ids), function (id) {
            self.remove(self.get(id));
        });
        _.each(_.difference(new_ids, old_ids), function (id) {
            var attrs = response[self.responseAttr][_.indexOf(new_ids, id)];
            self.push(new self.model(attrs));
        });

        // then any updates to the individual models that haven't been added or
        // removed
        _.each(_.intersection(new_ids, old_ids), function (id) {
            var attrs = response[self.responseAttr][_.indexOf(new_ids, id)];
            var model = self.get(id);
            model.set(attrs);
        });

        // this just instructs the fetch/add to not anything else:
        return [];
    },

    update: function() {
        var self = this;
        this.fetch({add: true, complete: function () {
            window.setTimeout(self.update, self.refreshInterval);
        }});
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
    responseAttr: 'devices'
});

var Request = Backbone.Model.extend({
    initialize: function(args) {
        this.set('selected', false);
    }
});

var Requests = UpdateableCollection.extend({
    url: function() {
        return '/api/request/list/' + (this.includeClosed ? '?include_closed=1' : '');
    },
    model: Request,
    responseAttr: 'requests',
    includeClosed: false
});

var PxeConfig = Backbone.Model.extend({
});

var PxeConfigs = Backbone.Collection.extend({
    url: '/api/bmm/pxe_config/list/?active_only=1',
    model: PxeConfig,
    parse: function(response) {
        return $.map(response.pxe_configs, function(name, id) { return { name: name, id: id }; });
    }
});

var LogLine = Backbone.Model.extend({
});

var Log = Backbone.Collection.extend({
    model: LogLine,
    initialize: function(args) {
        this.url = '/api/' + args['object'] + '/' + args['name'] + '/log/';
    },
    parse: function(response) {
        return response.log;
    }
});

// client-only models

var RenewDuration = Backbone.Model.extend({
    initialize: function(args) {
        this.set('renewDuration', '');
    }
});

var SelectedPxeConfig = Backbone.Model.extend({
    // currently-selected boot image in the <select>; name can be '' when no
    // image is selected
    initialize: function (args) {
        this.set('name', '');
    }
});

var CurrentB2gBase = Backbone.Model.extend({
    // current URL in the input box
    initialize: function (args) {
        this.set('b2gbase', '');
    }
});

var CurrentForceState = Backbone.Model.extend({
    // current URL in the input box
    initialize: function (args) {
        this.set('state', '');
    }
});

var DeviceJob = Backbone.Model.extend({
    initialize: function (args) {
        this.device = args.device;
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
        this.request = args.request;
        this.set('job_type', args.job_type);
        this.set('job_args', args.job_args);
        this.set('request_id', this.request.get('id'));
    },

    job_subject: function() {
        return 'request ' + this.get('request_id');
    }
});

var JobQueue = Backbone.Collection.extend({
    model: null,  // override after creation
});
