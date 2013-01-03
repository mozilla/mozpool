/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/*
 * Toolbar Controls
 */

var NewJobButtonView = Backbone.View.extend({
    tagName: 'button',

    initialize: function(args) {
        // if collection is defined, then a job will be submitted for each
        // selected item
        this.collection = args.collection;
        // text of the button
        this.buttonText = args.buttonText;
        // the type of the job to submit (recognized by controller.js)
        this.jobType = args.jobType;
        // a list of args that should be included in the job; their values
        // will be generated appropriately
        this.addJobArgs = args.addJobArgs;
        // list of control_state values that must be truthy for the button
        // to be enabled; 'selected' is treated specially, requiring that at
        // least one object in the list be selected
        this.disabledUnless = args.disabledUnless;
        // if truthy, submit comments, but only if set_comments is set
        this.submitComments = args.submitComments;

        _.bindAll(this, 'refreshButtonStatus', 'buttonClicked');

        if (this.collection) {
            this.collection.bind('change', this.refreshButtonStatus);
        }
        window.control_state.bind('change', this.refreshButtonStatus);
    },

    events: {
        'click': 'buttonClicked'
    },

    render: function() {
        this.$el.text(this.buttonText);
        this.refreshButtonStatus();
        return this;
    },

    refreshButtonStatus: function() {
        var self = this;

        // check through the args for disabledUnless
        var enabled = _.all(self.disabledUnless, function (u) {
            if (u === "selected") {
                rv = self.collection.any(function (m) { return m.get('selected'); });
            } else {
                rv = window.control_state.get(u);
            }
            return rv;
        });
        self.$el.attr('disabled', !enabled);
    },

    buttonClicked: function() {
        var self = this;
        if (!self.collection) {
            // make a job in general, without a model
            var jobs = self.makeJobs(null);
            _.each(jobs, function(j) { job_queue.push(j); });
        } else {
            // new job for each selected element
            var set_comments = window.control_state.get('set_comments')
                && (-1 != $.inArray('comments', self.addJobArgs));
            var comments = window.control_state.get('comments');

            self.collection.each(function (m) {
                if (m.get('selected')) {
                    var jobs = self.makeJobs(m);
                    _.each(jobs, function(j) { job_queue.push(j); });
                    m.set('selected', false);
                }
            });

            // uncheck the comments checkbox, so they're not applied next time
            window.control_state.set('set_comments', false);
        }
    },

    makeJobs: function(m) {
        var jobs = [ ];

        if (this.jobType) {
            var job = { model: m, job_type: this.jobType, job_args: {} };
            // munge addJobArgs into job_args
            _.each(this.addJobArgs, function(arg) {
                // special-case old_state; everything else just gets copied
                // from the control_state model
                if (arg === 'old_state') {
                    job.job_args[arg] = m.get('state');
                } else {
                    job.job_args[arg] = window.control_state.get(arg);
                }
            }, this);
            jobs.push(job);
        }

        // add a second job to set comments if necessary
        if (this.submitComments && window.control_state.get('set_comments')) {
            jobs.push({
                model: m,
                job_type: 'set-comments',
                job_args: { 'comments': window.control_state.get('comments') }
            });
        }

        return jobs;
    }
});

var TextView = Backbone.View.extend({
    tagName: 'input',
    initialize: function(args) {
        this.control_state_attribute = args.control_state_attribute;
        this.size = args.size;

        _.bindAll(this, 'valueChanged', 'modelChanged');
        window.control_state.bind('change', this.modelChanged);
        this.valueChanged = _.debounce(this.valueChanged, 100);
    },

    events: {
        'change': 'valueChanged',
        'keyup': 'valueChanged'
    },

    render: function() {
        this.$el.attr('type', 'text');
        this.$el.attr('size', this.size);
        this.modelChanged();
        return this;
    },

    valueChanged: function() {
        window.control_state.set(this.control_state_attribute, this.$el.val());
    },

    modelChanged: function() {
        this.$el.val(window.control_state.get(this.control_state_attribute));
    },

    setPlaceholder: function(placeholder) {
        this.$el.attr('placeholder', placeholder);
    }
});

var SelectView = Backbone.View.extend({
    tagName: 'select',
    collectionName: null,
    staticItem: null,
    controlStateAttr: null,

    initialize: function(args) {
        _.bindAll(this, 'refresh', 'selectChanged', 'controlStateChanged');

        // get the collection, now that it's loaded
        this.collection = window[this.collectionName];

        this.collection.bind('reset', this.refresh);
        this.collection.bind('change', this.refresh);
        window.control_state.bind('change', this.controlStateChanged);
    },

    events: {
        'change': 'selectChanged'
    },

    render: function() {
        this.refresh();

        // synchronize the control state to the select
        this.selectChanged();

        return this;
    },

    refresh: function() {
        var self = this;

        // remove existing options, then add the whole new list of them; we try to
        // restore the existing value, if it exists
        var old_val = self.$el.val();

        self.$el.empty();
        if (self.staticItem) {
            var opt = $('<option>');
            opt.attr('value', self.staticItem);
            opt.text(self.staticItem);
            self.$el.append(opt);
        }
        self.collection.each(function (pxe_config) {
            var opt = $('<option>');
            var name = pxe_config.get('name');
            opt.attr('value', name);
            opt.text(name);
            self.$el.append(opt);
        });

        self.$el.val(old_val);

        // read the value back and update the control state
        self.selectChanged();
    },

    controlStateChanged: function() {
        this.$el.val(window.control_state.get(this.controlStateAttr));
    },

    selectChanged: function() {
        window.control_state.set(this.controlStateAttr, this.$el.val());
    }
});

var ImageSelectView = SelectView.extend({
    collectionName: 'images',
    controlStateAttr: 'image'
});

var PxeConfigSelectView = SelectView.extend({
    collectionName: 'pxe_configs',
    controlStateAttr: 'pxe_config'
});

var MozpoolRequestedDeviceSelectView = SelectView.extend({
    collectionName: 'devicenames',
    controlStateAttr: 'device',
    staticItem: 'any'
});

var MozpoolRequestedEnvironmentSelectView = SelectView.extend({
    collectionName: 'environments',
    controlStateAttr: 'environment',
    staticItem: 'any'
});

var PleaseVerbView = SelectView.extend({
    collectionName: 'please_verbs',
    controlStateAttr: 'please_verb'
});

var IncludeClosedCheckboxView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
        this.valueChanged();
    },

    events: {
        'change': 'valueChanged'
    },

    valueChanged: function() {
        window.requests.includeClosed = this.$el.attr('checked') != undefined;
        window.requests.update();
    }
});

var CommentsView = Backbone.View.extend({
    tagName: 'span',
    initialize: function(args) {
        _.bindAll(this, 'valueChanged', 'checkboxChanged', 'modelChanged');
        window.control_state.bind('change', this.modelChanged);
        this.valueChanged = _.debounce(this.valueChanged, 100);
    },

    render: function() {
        var e;

        this.checkbox = e = $('<input>');
        e.attr('type', 'checkbox');
        e.change(this.checkboxChanged);
        this.$el.append(e);

        this.text = e = $('<input>');
        e.attr('type', 'text');
        e.attr('size', '80');
        e.change(this.valueChanged);
        e.keyup(this.valueChanged);
        this.$el.append(e);

        this.modelChanged();
        return this;
    },

    valueChanged: function() {
        var val = this.text.val();

        window.control_state.set('comments', val);

        // check the checkbox if it isn't already
        if (val && !window.control_state.get('set_comments')) {
            window.control_state.set('set_comments', true);
        }
    },

    checkboxChanged: function() {
        window.control_state.set('set_comments', this.checkbox.prop('checked') ? true : false);
    },

    modelChanged: function() {
        this.checkbox.prop('checked', window.control_state.get('set_comments'));
        this.text.val(window.control_state.get('comments'));
    }
});

var HelpView = Backbone.View.extend({
    tagName: 'div',

    initialize: function(args) {
        this.help_text = args.help_text;
    },

    render: function() {
        this.$el.addClass('help');
        this.$el.text(this.help_text);
        return this;
    }
});


