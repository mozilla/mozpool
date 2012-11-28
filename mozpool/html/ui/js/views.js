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
        { id: "state", title: "State" },
        { id: "links", title: "Links",
            renderFn: "renderLinks" },
    ],

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

var RequestTableView = TableView.extend({
    initialize: function(args) {
        args.collection = window.requests;
        args.checkboxRE = /request-(\d+)/;
        TableView.prototype.initialize.call(this, args);
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

var ActionButtonView = Backbone.View.extend({
    initialize: function(args) {
        this.collection = args.collection;
        _.bindAll(this, 'refreshButtonStatus', 'buttonClicked');
        this.collection.bind('change', this.refreshButtonStatus);
    },

    events: {
        'click': 'buttonClicked'
    },

    render: function() {
        this.refreshButtonStatus();
    },

    refreshButtonStatus: function() {
        // only enable the button if at least one device is selected
        var any_selected = this.collection.any(function (m) { return m.get('selected'); });
        this.$el.attr('disabled', !any_selected);
    },

    buttonClicked: function() {
        var self = this;
        window.devices.each(function (m) {
            if (m.get('selected')) {
                var job = self.makeJob(m);
                if (job) {
                    job_queue.push(job);
                }
                m.set('selected', false);
            }
        });
    },

    makeJob: function(model) {
        // subclasses override this
    }
});

var BmmPowerCycleButtonView = ActionButtonView.extend({
    initialize: function() {
        ActionButtonView.prototype.initialize.call(
            this, {collection: window.devices});
    },
    makeJob: function(m) {
        return {
            device: m,
            job_type: 'bmm-power-cycle',
            job_args: { pxe_config: window.selected_pxe_config.get('name'), config: {} }
        };
    }
});

var BmmPowerOffButtonView = ActionButtonView.extend({
    initialize: function() {
        ActionButtonView.prototype.initialize.call(
            this, {collection: window.devices});
    },
    makeJob: function(m) {
        return {
            device: m,
            job_type: 'bmm-power-off',
            job_args: {}
        }
    }
});

var LifeguardPleaseButtonView = ActionButtonView.extend({
    initialize: function() {
        ActionButtonView.prototype.initialize.call(
            this, {collection: window.devices});
        window.selected_pxe_config.bind('change', this.refreshButtonStatus);
    },
    makeJob: function(m) {
        var selected_pxe_config = window.selected_pxe_config.get('name');

        var job_type, job_args;
        if (selected_pxe_config) {
            // for now, we just always provides a b2g-style boot_config
            var b2gbase = window.current_b2gbase.get('b2gbase');
            var boot_config = {};
            if (b2gbase) {
                boot_config = { version: 1, b2gbase: b2gbase };
            };
            job_type = 'lifeguard-pxe-boot';
            job_args = { pxe_config: selected_pxe_config, boot_config: boot_config };
        } else {
            job_type = 'lifeguard-power-cycle';
            job_args = {};
        }

        return {
            device: m,
            job_type: job_type,
            job_args: job_args
        };
    },
    refreshButtonStatus: function() {
        // let the parent class handle enable/disable
        ActionButtonView.prototype.refreshButtonStatus.call(this);

        // and change the text based on what's selected
        var selected_pxe_config = window.selected_pxe_config.get('name');
        var button_text = selected_pxe_config ? "PXE Boot" : "Power Cycle";
        if (button_text != this.$el.text()) {
            this.$el.text(button_text);
        }
    }
});

var LifeguardForceStateButtonView = ActionButtonView.extend({
    initialize: function() {
        ActionButtonView.prototype.initialize.call(
            this, {collection: window.devices});
    },
    makeJob: function(m) {
        return {
            device: m,
            job_type: 'lifeguard-force-state',
            job_args: { old_state: m.get('state'), new_state: window.current_force_state.get('state') }
        };
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

var MozpoolRenewDurationView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
    },

    events: {
        'change': 'valueChanged',
        'keyup': 'valueChanged',
    },

    valueChanged: function() {
        window.current_renew_duration.set('duration', this.$el.val());
    }
});

var MozpoolCloseRequestsButtonView = ActionButtonView.extend({
    initialize: function() {
        ActionButtonView.prototype.initialize.call(
            this, {collection: window.requests});
    },

    buttonClicked: function() {
        window.requests.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    request: b,
                    job_type: 'mozpool-close-request'
                });
            }
        });
    }
});

var MozpoolRenewRequestsButtonView = ActionButtonView.extend({
    initialize: function() {
        ActionButtonView.prototype.initialize.call(
            this, {collection: window.requests});
        window.current_renew_duration.bind('change', this.refreshButtonStatus);
    },

    buttonClicked: function() {
        window.requests.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    request: b,
                    job_type: 'mozpool-renew-request',
                    job_args: { duration: window.current_renew_duration.get('duration') }
                });
            }
        });
    },

    refreshButtonStatus: function() {
        var duration = window.current_renew_duration.get('duration');
        if (duration == '' || isNaN(duration)) {
            this.$el.attr('disabled', 'disabled');
            return;
        }
        ActionButtonView.prototype.refreshButtonStatus.call(this);
    }
});

var MozpoolRequestedDeviceSelectView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'refresh', 'selectChanged');

        this.requested_device_views = [];
        window.devicenames.bind('reset', this.refresh);
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

    selectChanged: function() {
        window.selected_requested_device.set('name', this.$el.val());
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

var MozpoolRequestActionSelectView = Backbone.View.extend({
    events: {
        'change': 'selectChanged'
    },

    render: function() {
        this.selectChanged();
        return this;
    },

    selectChanged: function() {
        var selected = this.$el.val();
        window.selected_request_action.set('action', selected);
        if (selected == 'reimage') {
            $('#reimage-controls').show();
        } else {
            $('#reimage-controls').hide();
        }
    }
});

var MozpoolRequestAssigneeView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
    },

    events: {
        'change': 'valueChanged',
        'keyup': 'valueChanged',
    },

    valueChanged: function() {
        window.current_request_assignee.set('assignee', this.$el.val());
    }
});

var MozpoolRequestDurationView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
    },

    events: {
        'change': 'valueChanged',
        'keyup': 'valueChanged',
    },

    valueChanged: function() {
        window.current_request_duration.set('duration', this.$el.val());
    }
});

var MozpoolRequestSubmitButtonView = Backbone.View.extend({
    initialize: function() {
        _.bindAll(this, 'refreshButtonStatus', 'buttonClicked');
        window.selected_request_action.bind('change', this.refreshButtonStatus);
        window.current_request_assignee.bind('change', this.refreshButtonStatus);
        window.current_request_duration.bind('change', this.refreshButtonStatus);
        window.current_b2gbase.bind('change', this.refreshButtonStatus);
    },

    events: {
        'click': 'buttonClicked'
    },

    render: function() {
        this.refreshButtonStatus();
    },

    buttonClicked: function() {
        var job_args = {
            device: window.selected_requested_device.get('name'),
            duration: window.current_request_duration.get('duration'),
            assignee: window.current_request_assignee.get('assignee')
        };

        if (window.selected_request_action.get('action') == 'reimage') {
            job_args.b2gbase = window.current_b2gbase.get('b2gbase');
        }

        job_queue.push({
            job_type: 'mozpool-create-request',
            job_args: job_args
        });
    },

    refreshButtonStatus: function() {
        var disabled = false;
        var duration = window.current_request_duration.get('duration');
        if (duration == '' || isNaN(duration) ||
            !window.current_request_assignee.get('assignee') ||
            (window.selected_request_action.get('action') == 'reimage' && !window.current_b2gbase.get('b2gbase'))) {
            disabled = true;
        }

        this.$el.attr('disabled', disabled);
    }
});

var PxeConfigSelectView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'refresh', 'selectChanged');

        this.pxe_config_views = [];
        window.pxe_configs.bind('reset', this.refresh);
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
        $.each(self.pxe_config_views, function (v) { v.remove() });
        window.pxe_configs.each(function (pxe_config) {
            var v = new PxeConfigOptionView({ model: pxe_config });
            $(self.el).append(v.render().el);
            self.pxe_config_views.push(v);
        });
    },

    selectChanged: function() {
        window.selected_pxe_config.set('name', this.$el.val());
    }
});

var B2gBaseView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
    },

    events: {
        'change': 'valueChanged',
        'keyup': 'valueChanged'
    },

    valueChanged: function() {
        window.current_b2gbase.set('b2gbase', this.$el.val());
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

var ForceStateView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
    },

    events: {
        'change': 'valueChanged'
    },

    valueChanged: function() {
        window.current_force_state.set('state', this.$el.val());
    }
});

var JobQueueView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'refresh');

        window.job_queue.bind('change', this.refresh);
        window.job_queue.bind('add', this.refresh);
        window.job_queue.bind('remove', this.refresh);
    },

    render: function() {
        this.refresh();
        return this;
    },

    refresh: function() {
        var length = window.job_queue.length;

        if (length == 1) {
            this.$el.text('1 job queued');
        } else if (!length) {
            this.$el.text('no jobs queued');
        } else {
            this.$el.text(length + ' jobs queued');
        }
    }
});

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

var ToolbarView = Backbone.View.extend({
    tagName: 'div',

    render: function() {
        // make it slightly opaque so we can see any objects hidden behind it
        $('div#toolbar').css('opacity', '.95');

        // and set the body's margin-bottom to the height of the toolbar
        var height = $('#toolbar').height();
        height += 10; // 5px padding
        $('body').css('margin-bottom', height + 'px');
    }
});

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

