/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/*
 * Toolbar
 */

var ToolbarView = Backbone.View.extend({
    tagName: 'div',
    initialize: function(args) {
        this.subview_classes = args['subview_classes'];
        _.bindAll(this, 'activateView', 'render', 'refresh');
    },

    render: function() {
        var self = this;
        self.subviews = [];

        var view = new JobQueueView();
        this.$el.append(view.render().$el);

        var ul = $('<ul>');
        ul.attr('class', 'toolbar-actions');
        self.$el.append(ul)

        _.each(self.subview_classes, function(cls) {
            var sv_div = $('<div>');
            sv_div.attr('class', 'toolbar-action');
            self.$el.append(sv_div)

            var sv = new cls({ el: sv_div });
            self.subviews.push(sv);
            sv.render();

            var li = $('<li>');
            li.text(sv.title);
            li.click(function() {
                self.activateView(sv);
            });
            sv.$li = li;
            ul.append(li);
        });

        self.activateView(self.subviews[0]);

        // make it slightly opaque so we can see any objects hidden behind it
        $('div#toolbar').css('opacity', '.95');

        self.refresh();
        return self;
    },

    activateView: function(subview) {
        _.each(this.subviews, function (sv) {
            if (sv != subview) {
                sv.$el.hide();
                sv.$li.removeClass('active');
            }
        });
        subview.$el.show();
        subview.$li.addClass('active');

        this.refresh();
    },

    refresh: function() {
        // reset the body's margin-bottom to the height of the toolbar plus some padding
        var height = $('#toolbar').height();
        height += 10; // 5px padding
        $('body').css('margin-bottom', height + 'px');
    }
});

/*
 * Toolbar Actions
 */

var BmmPxeBootView = Backbone.View.extend({
    name: 'pxe-boot',
    title: 'PXE Boot',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This view allows you to manually PXE boot a device.  ' +
            'It is almost always better to use lifeguard to do this, as it can track state and retry.'});
        this.$el.append(view.render().$el);

        this.$el.append('PXE Config: ');

        view = new PxeConfigSelectView({});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'PXE Boot',
            collection: window.devices,
            disabledUnless: [ 'pxe_config', 'boot_config_raw', 'selected' ],
            jobType: 'bmm-power-cycle',
            addJobArgs: ['pxe_config', 'boot_config_raw'],
            submitComments: true});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Boot Config (JSON): ');

        view = new TextView({ control_state_attribute: 'boot_config_raw', size: 80 });
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Update Comments: ');
        view = new CommentsView();
        this.$el.append(view.render().$el);
    },
});

var BmmPowerControlView = Backbone.View.extend({
    name: 'power-control',
    title: 'Power Control',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This view allows you to directly control the power to a device.  ' +
            'Note that doing so may confuse lifeguard if it is actively managing the device.'});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Power Cycle',
            collection: window.devices,
            disabledUnless: [ 'selected' ],
            jobType: 'bmm-power-cycle',
            addJobArgs: [],
            submitComments: true});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Power Off',
            collection: window.devices,
            disabledUnless: [ 'selected' ],
            jobType: 'bmm-power-off',
            addJobArgs: [],
            submitComments: true});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Update Comments: ');
        view = new CommentsView();
        this.$el.append(view.render().$el);
    },
});

var BmmEnvironmentView = Backbone.View.extend({
    name: 'env',
    title: 'Environment',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This view allows you to update devices\' environment.'});
        this.$el.append(view.render().$el);

        // TODO: this will need a checkbox like comments, eventually
        this.$el.append('Environment: ');
        view = new TextView({ control_state_attribute: 'environment', size: 20 });
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Update',
            collection: window.devices,
            disabledUnless: [ 'environment', 'selected' ],
            jobType: 'set-environment',
            addJobArgs: ['environment']});
        this.$el.append(view.render().$el);
    },
});

var UpdateCommentsView = Backbone.View.extend({
    name: 'comments',
    title: 'Comments',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This view allows you to comment on one or more devices.  ' +
            'To clear out old comments, tick the checkbox but leave the text field blank.'});
        this.$el.append(view.render().$el);

        this.$el.append('Update Comments: ');
        view = new CommentsView();
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Comment',
            collection: window.devices,
            disabledUnless: [ 'set_comments', 'selected' ],
            submitComments: true})
        this.$el.append(view.render().$el);
    },
});

var LifeguardPleaseView = Backbone.View.extend({
    name: 'please',
    title: 'Please..',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This advanced tool requests "managed" operations from lifeguard.  ' +
            'Power-cycling requires no arguments (PXE config and boot config are ignored).  ' +
            'PXE-booting requires a PXE config, and depending on the PXE config may also require a boot config ' +
            '(e.g., B2G requires a boot config with a "b2gbase" key).'});
        this.$el.append(view.render().$el);

        this.$el.append(new PleaseVerbView().render().$el);

        this.$el.append(' with PXE config ')

        view = new PxeConfigSelectView({});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Go',
            collection: window.devices,
            disabledUnless: [ 'please_verb', 'selected' ],
            jobType: 'lifeguard-please',
            addJobArgs: ['please_verb', 'pxe_config', 'boot_config_raw' ],
            submitComments: true});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Boot Config (JSON): ');

        view = new TextView({ control_state_attribute: 'boot_config_raw', size: 80 });
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Update Comments: ');
        view = new CommentsView();
        this.$el.append(view.render().$el);
    },
});

var LifeguardForceStateView = Backbone.View.extend({
    name: 'force',
    title: 'Force State',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This advanced tool forces a device into a specified state.  ' +
            'This can be used to "lock out" a device, or to return a device from that state.'});
        this.$el.append(view.render().$el);

        this.$el.append('State:')
        view = new TextView({ control_state_attribute: 'new_state', size: 20 });
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Force State',
            collection: window.devices,
            disabledUnless: [ 'new_state', 'selected' ],
            jobType: 'lifeguard-force-state',
            addJobArgs: ['old_state', 'new_state'],
            submitComments: true});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Update Comments: ');
        view = new CommentsView();
        this.$el.append(view.render().$el);
    },
});

var MozpoolCloseRequestsView = Backbone.View.extend({
    name: 'close-requests',
    title: 'Close Requests',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This tool allows you to close requests before their expiration time.'});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Close Requests',
            collection: window.requests,
            disabledUnless: [ 'selected' ],
            jobType: 'mozpool-close-request',
            addJobArgs: []});
        this.$el.append(view.render().$el);
    },
});

var MozpoolRenewRequestsView = Backbone.View.extend({
    name: 'renew-requests',
    title: 'Renew Requests',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This tool allows you to renew requests, extending their expiration time.'});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Renew Requests',
            collection: window.requests,
            disabledUnless: [ 'renew_duration', 'selected' ],
            jobType: 'mozpool-renew-request',
            addJobArgs: [ 'renew_duration' ]});
        this.$el.append(view.render().$el);

        this.$el.append(' for ');

        view = new TextView({ control_state_attribute: 'renew_duration', size: 6 });
        this.$el.append(view.render().$el);

        this.$el.append(' seconds');
    },
});

var MozpoolNewRequestView = Backbone.View.extend({
    name: 'new-request',
    title: 'New Request',

    render: function() {
        var view;

        view = new HelpView({help_text:
            'This tool allows you to request a new device.  ' +
            'It currently only supports requesting devices with a B2G image.  ' +
            'You may request "any" device, which allows mozpool to select a suitable device, or request a specific device.  ' +
            'The device will be yours for the given duration, after which time it will be returned to the pool.  ' +
            'Enter your email address in the "assigned to" field.  ' +
            'The B2G Base URL should point to a directory containing three partition tarballs.'});
        this.$el.append(view.render().$el);

        this.$el.append('Request device ');
        view = new MozpoolRequestedDeviceSelectView();
        this.$el.append(view.render().$el);

        this.$el.append(' in environment ');
        view = new MozpoolRequestedEnvironmentSelectView();
        this.$el.append(view.render().$el);

        this.$el.append(' for ');

        view = new TextView({ control_state_attribute: 'request_duration', size: 6 });
        this.$el.append(view.render().$el);

        this.$el.append(' seconds ');

        view = new NewJobButtonView({
            buttonText: 'Request',
            jobType: 'mozpool-create-request',
            addJobArgs: [ 'image', 'request_duration', 'assignee', 'b2gbase', 'device', 'environment' ],
            disabledUnless: [ 'image', 'request_duration', 'assignee', 'b2gbase', 'device', 'environment' ],
        });
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Assigned to ');

        view = new TextView({ control_state_attribute: 'assignee', size: 30 });
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('With B2G Base URL ');

        view = new TextView({ control_state_attribute: 'b2gbase', size: 80 });
        this.$el.append(view.render().$el);
    },
});

