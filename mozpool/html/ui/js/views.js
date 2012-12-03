/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

var TableView = Backbone.View.extend({
    tagName: 'div',

    columns: [
    ],

    collection: null,

    events: {
        'click input' : 'checkboxClicked',
    },

    initialize: function(args) {
        this.collection = args.collection;
        this.checkboxRE = args.checkboxRE;
        _.bindAll(this, 'render', 'modelAdded', 'domObjectChanged',
                  'checkboxClicked');

        this.collection.bind('add', this.modelAdded);
        // remove handled by TableRowView

        this.tableRowViews = [];
    },

    render: function() {
        var self = this;

        // dataTable likes to add sibling nodes, so add the table within
        // the enclosing div, this.el
        $(this.el).append('<table class="display" ' +
            'cellspacing="0" cellpadding="0" border="0"></table>');

        // calculate the columns for the table; this is coordinated with
        // the data for the table in the view below

        // hidden id column
        var aoColumns = [];
        
        // column storing the id
        aoColumns.push({ bVisible: false });

        // data columns
        aoColumns = aoColumns.concat(
            this.columns.map(function(col) {
                var rv = { sTitle: col.title, sClass: 'col-' + col.id };
                if (col.renderFn) {
                    rv.bUseRendered = false;
                    rv.fnRender = function(oObj) {
                        var model = self.collection.get(oObj.aData[0]);
                        return self[col.renderFn].apply(self, [ model ]);
                    };
                } 
                if (col.sClass) {
                    rv.sClass = col.sClass;
                }
                return rv;
            }));

        // create an empty table
        var dtArgs = {
            aoColumns: aoColumns,
            bJQueryUI: true,
            bAutoWidth: false,
            bPaginate: false,
            bInfo: false // hide table info
        };

        this.dataTable = this.$('table').dataTable(dtArgs);

        // transplant the search box from the table header to our toolbar
        this.$('.dataTables_filter').detach().appendTo('#header');

        // attach a listener to the entire table, to catch events bubbled up from
        // the checkboxes
        this.$('table').change(this.domObjectChanged);

        // add a 'redraw' method to the dataTable, debounced so we don't redraw too often
        this.dataTable.redraw = _.debounce(function () { self.dataTable.fnDraw(false); }, 100);

        // now simulate an "add" for every element currently in the model
        this.collection.each(function(m) { self.modelAdded(m); });

        return this;
    },

    modelAdded: function (m) {
        //conosle.dir(m);
        this.tableRowViews.push(new TableRowView({
            model: m,
            dataTable: this.dataTable,
            parentView: this
        }));
        // no need to render the view; dataTables already has the

        // schedule a (debounced) redraw
        this.dataTable.redraw();
    },

    rowDeleted: function(idx) {
        var self = this;
        $.each(self.tableRowViews, function(i, v) {
            if (v.row_index > idx) {
                v.row_index--;
            }
        });
    },

    // convert a TR element (not a jquery selector) to its position in the table
    getTablePositionFromTrElement: function(elt) {
        // this gets the index in the table data
        var data_idx = this.dataTable.fnGetPosition(elt);

        // now we search for that index in aiDisplayMaster to find out where it's displayed
        var aiDisplayMaster = this.dataTable.fnSettings().aiDisplayMaster;
        return aiDisplayMaster.indexOf(data_idx);
    },

    checkboxClicked: function (e) {
        var tr = $(e.target).parent().parent().get(0);

        // handle shift-clicking to select a range
        if (e.shiftKey &&
                // the event propagates *after* the state changed, so if this is checked now,
                // that's due to this click
                e.target.checked &&
                // and only do this if we have another click to pair it with
                this.lastClickedTr) {
            var target = e.target;

            var from_pos = this.getTablePositionFromTrElement(tr);
            var to_pos = this.getTablePositionFromTrElement(this.lastClickedTr);

            // sort the two
            if (from_pos > to_pos) {
                var t;
                t = from_pos;
                from_pos = to_pos;
                to_pos = t;
            }

            // check everything between from and to
            var aiDisplayMaster = this.dataTable.fnSettings().aiDisplayMaster;
            while (from_pos <= to_pos) {
                // convert the table position to a model
                var data_idx = aiDisplayMaster[from_pos];
                var id = this.dataTable.fnGetData(data_idx, 0);
                this.collection.get(id).set('selected', 1);
                from_pos++;
            }
        } 

        // store the last click for use if the next is with 'shift'
        this.lastClickedTr = tr;
    },

    domObjectChanged: function(evt) {
        // make sure this is a checkbox
        if (evt.target.nodeName != 'INPUT') {
            return;
        }

        // figure out the id
        var dom_id = evt.target.id;
        var id = this.checkboxRE.exec(dom_id)[1];
        if (id == '') {
            return;
        }

        // get the checked status
        var checked = this.$('#' + dom_id).is(':checked')? true : false;

        var model = this.collection.get(id);
        model.set('selected', checked);
    }
});

var DeviceTableView = TableView.extend({
    initialize: function(args) {
        args.collection = window.devices;
        args.checkboxRE = /device-(\d+)/;
        TableView.prototype.initialize.call(this, args);
    },

    renderSelected: function(model) {
        var checked = '';
        if (model.get('selected')) {
            checked = ' checked=1';
        }
        var checkbox = '<input type="checkbox" id="device-' + model.get('id') + '"' + checked + '>';
        return checkbox;
    },

    renderFqdn: function (model) {
        var fqdn = model.get('fqdn');
        var name = model.get('name');

        // if fqdn starts with the name and a dot, just return that
        if (fqdn.slice(0, name.length + 1) != name + ".") {
            fqdn = fqdn + " (" + name + ")";
        }
        return fqdn;
    },

    renderMac: function (model) {
        var mac_address = model.get('mac_address');
        var with_colons = mac_address.split(/(?=(?:..)+$)/).join(":");
        return '<tt>' + with_colons + '</tt>';
    },

    renderImgServer: function (model) {
        var imaging_server = model.get('imaging_server');

        return "<small>" + imaging_server + "</small>";
    },

    renderRelayInfo: function (model) {
        var relay_info = model.get('relay_info');

        return "<small>" + relay_info + "</small>";
    },

    renderLinks: function (model) {
        var inv_a = $('<a/>', {
            // TODO get this link from config.ini
            href: 'https://inventory.mozilla.org/en-US/systems/show/' + model.get('inventory_id') + '/',
            text: 'inv',
            target: '_blank'
        });
        var log_a = $('<a/>', {
            href: 'log.html?device=' + model.get('name'),
            text: 'log',
            target: '_blank'
        });
        // for each, wrap in a div and extract the contents as a string
        return "[" + $('<div>').append(log_a).html() + "]"
             + '&nbsp;'
             + "[" + $('<div>').append(inv_a).html() + "]";
    },
});

var LifeguardTableView = DeviceTableView.extend({
    columns: [
        { id: "selected", title: '', bSortable: false,
            sClass: 'rowcheckbox', renderFn: "renderSelected" },
        { id: "name", title: "Name" },
        { id: "state", title: "State" },
        { id: "last_pxe_config", title: "PXE Cfg" },
        { id: "comments", title: "Comments" },
        { id: "links", title: "Links",
            renderFn: "renderLinks" },
    ],
});

var BMMTableView = DeviceTableView.extend({
    columns: [
        { id: "selected", title: '', bSortable: false,
            sClass: 'rowcheckbox', renderFn: "renderSelected" },
        { id: "fqdn", title: "FQDN",
            renderFn: "renderFqdn" },
        { id: "mac_address", title: "MAC",
            renderFn: "renderMac" },
        { id: "imaging_server", title: "Imaging Server",
            renderFn: "renderImgServer" },
        { id: "relay_info", title: "Relay Info",
            renderFn: "renderRelayInfo" },
        { id: "comments", title: "Comments" },
        { id: "links", title: "Links",
            renderFn: "renderLinks" },
    ],
});

var RequestTableView = TableView.extend({
    initialize: function(args) {
        args.collection = window.requests;
        args.checkboxRE = /request-(\d+)/;
        TableView.prototype.initialize.call(this, args);

        // get our "include closed" checkbox hooked up
        new IncludeClosedCheckboxView({ el: $('#include-closed-checkbox') }).render();
    },

    columns: [
        { id: "selected", title: '', bSortable: false,
            sClass: 'rowcheckbox', renderFn: "renderSelected" },
        { id: "id", title: "ID" },
        { id: "requested_device", title: "Requested Device",
            renderFn: "renderRequested" },
        { id: "assigned_device", title: "Assigned Device",
            renderFn: "renderAssigned" },
        // include creation time!
        { id: "state", title: "State" },
        { id: "expires", title: "Expires (UTC)", renderFn: "renderExpires" },
        { id: "imaging_server", title: "Server" },
        { id: "links", title: "Links", renderFn: "renderLinks" },
    ],

    renderSelected: function(model) {
        var checked = '';
        if (model.get('selected')) {
            checked = ' checked=1';
        }
        var disabled = '';
        if (model.get('state') == 'closed') {
            disabled = ' disabled=1';
        }
        var checkbox = '<input type="checkbox" id="request-' + model.get('id') + '"' + checked + disabled + '>';
        return checkbox;
    },

    renderDeviceLink: function(deviceName)
    {
        return '<a href="lifeguard.html">' + deviceName + '</a>';
    },

    renderAssigned: function(model)
    {
        var assignedDevice = model.get('assigned_device');
        if (!assignedDevice) {
            return '-';
        }
        return this.renderDeviceLink(assignedDevice) + ' (' +
            model.get('device_state') + ')';
    },

    renderRequested: function(model)
    {
        var requestedDevice = model.get('requested_device');
        if (requestedDevice == 'any') {
            return requestedDevice;
        }
        return this.renderDeviceLink(requestedDevice);
    },

    renderExpires: function(model) {
        // a little more readable than what is returned from the server
        return model.get('expires').replace('T', ' ').split('.')[0];
    },

    renderLinks: function(model) {
        var log_a = $('<a/>', {
            href: 'log.html?request=' + model.get('id'),
            text: 'log',
            target: '_blank'
        });
        // for each, wrap in a div and extract the contents as a string
        return "[" + $('<div>').append(log_a).html() + "]";
    },
});

// A class to represent each row in a TableView.  Because DataTables only allow
// strings in the cells, there's not much to do here -- all of the action is
// above.
var TableRowView = Backbone.View.extend({
    initialize: function(args) {
        this.dataTable = args.dataTable;
        this.parentView = args.parentView;

        _.bindAll(this, 'modelChanged');
        _.bindAll(this, 'modelRemoved');

        // set up the row datal put the id in the hidden column 0
        var model = this.model;
        var row = [ model.id ];
        row = row.concat(
            $.map(this.parentView.columns, function(col, i) {
                return String(model.get(col.id) || '');
            }));

        // insert into the table and store the index
        var row_indexes = this.dataTable.fnAddData(row, false);
        this.row_index = row_indexes[0];

        this.model.bind('change', this.modelChanged);
        this.model.bind('remove', this.modelRemoved);
    },

    modelChanged: function() {
        var self = this;
        var lastcol = self.parentView.columns.length - 1;

        $.each(self.parentView.columns, function (i, col) {
            var val = self.model.get(col.id);
            if (val === null) { val = ''; } // translate null to a string
            self.dataTable.fnUpdate(String(val),
                self.row_index,
                i+1, // 1-based column (column 0 is the hidden id)
                false, // don't redraw
                (i === lastcol)); // but update data structures on last col
        });

        // schedule a redraw, now that everything is updated
        self.dataTable.redraw();
    },

    modelRemoved: function() {
        this.dataTable.fnDeleteRow(this.row_index);
        this.parentView.rowDeleted(this.row_index);
        this.dataTable.redraw();
    },
});

/*
 * Logfiles
 */

var LogView = Backbone.View.extend({
    tagName: 'pre',

    // NOTE: for now, this just renders the initial model contents; it does not update
    render: function() {
        var self = this;
        window.log.each(function(l, idx) {
            var span;
            var line = $('<div>');
            line.attr('class', (idx % 2)? 'odd' : 'even');
            self.$el.append(line);

            span = $('<span>')
            span.attr('class', 'timestamp');
            span.text(l.get('timestamp'));
            line.append(span);
            line.append(' ');

            span = $('<span>')
            span.attr('class', 'source');
            span.text(l.get('source'));
            line.append(span);
            line.append(' ');

            span = $('<span>')
            span.attr('class', 'message');
            span.text(l.get('message'));
            line.append(span);
        });
    }
});

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
            disabled_unless: [ 'pxe_config', 'boot_config', 'selected' ],
            job_type: 'bmm-power-cycle',
            job_args: ['pxe_config', 'boot_config_raw', 'comments']});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Boot Config (JSON): ');

        view = new TextView({ control_state_attribute: 'boot_config', size: 80 });
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
            disabled_unless: [ 'selected' ],
            job_type: 'bmm-power-cycle',
            job_args: [ 'comments' ]});
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Power Off',
            collection: window.devices,
            disabled_unless: [ 'selected' ],
            job_type: 'bmm-power-off',
            job_args: [ 'comments' ]});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Update Comments: ');
        view = new CommentsView();
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
            disabled_unless: [ 'selected', 'set_comments' ],
            // no job_type, as there's nothing to do beyond comments
            job_args: ['comments']});
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
            disabled_unless: [ 'please_verb', 'selected' ],
            job_type: 'lifeguard-please',
            job_args: ['please_verb', 'pxe_config', 'boot_config_raw', 'comments']});
        this.$el.append(view.render().$el);

        this.$el.append($('<br>'));
        this.$el.append('Boot Config (JSON): ');

        view = new TextView({ control_state_attribute: 'boot_config', size: 80 });
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
        view = new TextView({ control_state_attribute: 'state', size: 20 });
        this.$el.append(view.render().$el);

        view = new NewJobButtonView({
            buttonText: 'Force State',
            collection: window.devices,
            disabled_unless: [ 'state', 'selected' ],
            job_type: 'lifeguard-force-state',
            job_args: ['old_state', 'new_state', 'comments']});
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
            disabled_unless: [ 'selected' ],
            job_type: 'mozpool-close-request',
            job_args: []});
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
            disabled_unless: [ 'renew_duration', 'selected' ],
            job_type: 'mozpool-renew-request',
            job_args: [ 'renew_duration' ]});
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

        this.$el.append(' for ');

        view = new TextView({ control_state_attribute: 'request_duration', size: 6 });
        this.$el.append(view.render().$el);

        this.$el.append(' seconds ');

        view = new NewJobButtonView({
            buttonText: 'Request',
            job_type: 'mozpool-create-request',
            job_args: [ 'image', 'request_duration', 'assignee', 'b2gbase', 'device' ],
            disabled_unless: [ 'image', 'request_duration', 'assignee', 'b2gbase', 'device' ],
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

/*
 * Toolbar Controls
 *
 * N.B. Unlike other views here, these create their own elements
 */

var NewJobButtonView = Backbone.View.extend({
    tagName: 'button',

    initialize: function(args) {
        this.collection = args.collection;
        this.buttonText = args.buttonText;
        this.job_type = args.job_type;
        this.job_args = args.job_args;
        this.disabled_unless = args.disabled_unless;

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

        // check through the args for disabled_unless
        var enabled = _.all(self.disabled_unless, function (u) {
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
            var job = self.makeJob(null);
            job_queue.push(job);
        } else {
            // new job for each selected element
            var set_comments = window.control_state.get('set_comments')
                && (-1 != $.inArray('comments', self.job_args));
            var comments = window.control_state.get('comments');

            self.collection.each(function (m) {
                if (m.get('selected')) {
                    if (self.job_type) {
                        var job = self.makeJob(m);
                        job_queue.push(job);
                    }

                    // if comments are requested, add a new job for those, too
                    if (set_comments) {
                        job_queue.push({
                            model: m,
                            job_type: 'set-comments',
                            job_args: { 'comments': comments }
                        });
                    }

                    m.set('selected', false);
                }
            });

            // uncheck the comments checkbox, so they're not applied next time
            window.control_state.set('set_comments', false);
        }
    },

    makeJob: function(m) {
        var job_args = {};
        // TODO: yikes, this is a little overwrought and due for a refactor..
        _.each(this.job_args, function(arg) {
            if (arg === 'pxe_config') {
                job_args.pxe_config = window.control_state.get('pxe_config');
                if (!('config' in job_args)) {
                    job_args.config = {};
                }
            } else if (arg === 'boot_config_raw') {
                job_args.boot_config_raw = window.control_state.get('boot_config');
            } else if (arg === 'please_verb') {
                job_args.please_verb = window.control_state.get('please_verb');
            } else if (arg === 'old_state') {
                job_args.old_state = m.get('state');
            } else if (arg === 'new_state') {
                job_args.new_state = window.control_state.get('state');
            } else if (arg === 'renew_duration') {
                job_args.duration = window.control_state.get('renew_duration');
            } else if (arg === 'device') {
                job_args.device = window.control_state.get('device');
            } else if (arg === 'request_duration') {
                job_args.duration = window.control_state.get('request_duration');
            } else if (arg === 'assignee') {
                job_args.assignee = window.control_state.get('assignee');
            } else if (arg === 'image') {
                job_args.image = window.control_state.get('image');
            } else if (arg === 'b2gbase') {
                job_args.b2gbase = window.control_state.get('b2gbase');
            }
        });
        return { model: m, job_type: this.job_type, job_args: job_args };
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
    }
});

var PxeConfigSelectView = Backbone.View.extend({
    tagName: 'select',
    initialize: function(args) {
        _.bindAll(this, 'refresh', 'selectChanged', 'modelChanged');

        this.pxe_config_views = [];
        window.pxe_configs.bind('reset', this.refresh);
        window.control_state.bind('change', this.modelChanged);
    },

    events: {
        'change': 'selectChanged'
    },

    render: function() {
        this.refresh();
        if (window.control_state.get('pxe_config') == '') {
            // the select will have picked one; use that
            this.selectChanged();
        }
        return this;
    },

    refresh: function() {
        var self = this;

        // remove existing views, then add the whole new list of them
        $.each(self.pxe_config_views, function (v) { v.remove() });
        window.pxe_configs.each(function (pxe_config) {
            var v = new PxeConfigOptionView({ model: pxe_config });
            self.$el.append(v.render().el);
            self.pxe_config_views.push(v);
        });
    },

    modelChanged: function() {
        this.$el.val(window.control_state.get('pxe_config'));
    },

    selectChanged: function() {
        window.control_state.set('pxe_config', this.$el.val());
    }
});

var PxeConfigOptionView = Backbone.View.extend({
    tagName: 'option',

    initialize: function() {
        _.bindAll(this, 'render');
    },

    render: function() {
        $(this.el).attr('value', this.model.get('name')).html(this.model.get('name'));
        return this;
    }
});

var PleaseVerbView = Backbone.View.extend({
    tagName: 'select',

    verbs: [ 'please_pxe_boot', 'please_power_cycle' ],

    initialize: function(args) {
        _.bindAll(this, 'refresh', 'selectChanged', 'modelChanged');
        window.control_state.bind('change', this.modelChanged);
    },

    events: {
        'change': 'selectChanged'
    },

    render: function() {
        this.refresh();
        if (window.control_state.get('please_verb') == '') {
            // the select will have picked one; use that
            this.selectChanged();
        }
        return this;
    },

    refresh: function() {
        var self = this;

        _.each(self.verbs, function (verb) {
            var opt = $('<option>');
            opt.attr('value', verb);
            opt.text(verb);
            self.$el.append(opt);
        });
    },

    modelChanged: function() {
        this.$el.val(window.control_state.get('please_verb'));
    },

    selectChanged: function() {
        window.control_state.set('please_verb', this.$el.val());
    }
});

var MozpoolRequestedDeviceSelectView = Backbone.View.extend({
    tagName: 'select',

    initialize: function(args) {
        _.bindAll(this, 'refresh', 'selectChanged', 'modelChanged');

        this.requested_device_views = [];
        window.devicenames.bind('reset', this.refresh);
        window.control_state.bind('change', this.modelChanged);
    },

    events: {
        'change': 'selectChanged'
    },

    render: function() {
        this.refresh();
        return this;
    },

    refresh: function() {
        var self = this;

        // remove existing views, then add the whole new list of them
        $.each(self.requested_device_views, function (v) { v.remove(); });
        window.devicenames.each(function (device) {
            var v = new MozpoolRequestedDeviceOptionView({ model: device });
            $(self.el).append(v.render().el);
            self.requested_device_views.push(v);
        });
    },

    modelChanged: function() {
        this.$el.val(window.control_state.get('device'));
    },

    selectChanged: function() {
        window.control_state.set('device', this.$el.val());
    }
});

var MozpoolRequestedDeviceOptionView = Backbone.View.extend({
    tagName: 'option',

    initialize: function() {
        _.bindAll(this, 'render');
    },

    render: function() {
        $(this.el).attr('value', this.model.get('id')).html(this.model.get('id'));
        return this;
    }
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

/*
 * Header
 */

var HeaderView = Backbone.View.extend({
    tagName: 'div',

    render: function() {
        // make it slightly opaque so we can see any objects hidden behind it
        $('div#header').css('opacity', '.95');

        // and set the body's margin-bottom to the height of the header
        var height = $('#header').height();
        $('body').css('margin-top', height + 'px');
    }
});

var JobQueueView = Backbone.View.extend({
    tagType: 'div',
    initialize: function(args) {
        _.bindAll(this, 'refresh');

        window.job_queue.bind('change', this.refresh);
        window.job_queue.bind('add', this.refresh);
        window.job_queue.bind('remove', this.refresh);
    },

    render: function() {
        this.$el.addClass('job-queue');
        this.$el.css('float', 'right');
        this.qlen = $('<span>');
        this.$el.append(this.qlen);

        this.refresh();
        return this;
    },

    refresh: function() {
        var length = window.job_queue.length;

        if (length == 1) {
            this.qlen.text('1 job queued');
        } else if (!length) {
            this.qlen.text('no jobs queued');
        } else {
            this.qlen.text(length + ' jobs queued');
        }
    }
});

