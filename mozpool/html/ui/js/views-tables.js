/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

var TableView = Backbone.View.extend({
    tagName: 'div',

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
        { id: "last_image", title: "Image" , renderFn: "renderImage"},
        { id: "comments", title: "Comments" },
        { id: "links", title: "Links",
            renderFn: "renderLinks" },
    ],

    renderImage: function(model) {
        var image = model.get('last_image');
        var bootConfig = model.get('boot_config');
        if (bootConfig) {
            bootConfig = JSON.parse(bootConfig);
        }
        if (!$.isEmptyObject(bootConfig)) {
            image += '&dagger;';
        }
        return image;
    }
});

var BMMTableView = DeviceTableView.extend({
    columns: [
        { id: "selected", title: '', bSortable: false,
            sClass: 'rowcheckbox', renderFn: "renderSelected" },
        { id: "fqdn", title: "FQDN",
            renderFn: "renderFqdn" },
        { id: "environment", title: "Environment" },
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
        { id: "assignee", title: "Assignee" },
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


