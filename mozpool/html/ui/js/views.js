var TableView = Backbone.View.extend({
    tagName: 'div',
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
            renderFn: "renderInvLink" },
    ],

    initialize: function(args) {
        this.refresh = $.proxy(this, 'refresh');
        this.render = $.proxy(this, 'render');
        _.bindAll(this, 'domObjectChanged');

        window.devices.bind('refresh', this.refresh);
    },

    render: function() {
        var self = this;

        // dataTable likes to add sibling nodes, so add the table within
        // the enclosing div, this.el
        $(this.el).append('<table class="display" ' +
            'cellspacing="0" cellpadding="0" border="0"></table>');

        // calculate the columns for the table; this is coordinated with
        // the data for the table in refresh(), below

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
                        var model = window.devices.get(oObj.aData[0]);
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
        this.refresh();

        // transplant the search box from the table header to our toolbar
        this.$('.dataTables_filter').detach().appendTo('#toolbar');

        // attach a listener to the entire table, to catch events bubbled up from
        // the checkboxes
        this.$('table').change(this.domObjectChanged);

        return this;
    },

    refresh : function (args) {
        var self = this;

        var newData = window.devices.map(function(instance_model) {
            // put the id in the hidden column 0
            var row = [ instance_model.id ];
            // data columns
            row = row.concat(
                $.map(self.columns, function(col, i) {
                    return String(instance_model.get(col.id) || '');
                }));
            return row;
        });

        // clear (without drawing) and add the new data
        self.dataTable.fnClearTable(false);
        self.dataTable.fnAddData(newData);
        $.each(self.dataTable.fnGetNodes(), function (i, tr) {
            var row = self.dataTable.fnGetData(tr);
            var instance_model = window.devices.get(row[0]);
            var view = new TableRowView({
                model: instance_model,
                el: tr,
                dataTable: self.dataTable,
                parentView: self
            });
            view.render();
        });
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

    renderInvLink: function (model) {
        var a = $('<a/>', {
            // TODO get this link from config.ini
            href: 'https://inventory.mozilla.org/en-US/systems/show/' + model.get('inventory_id') + '/',
            text: 'inv'
        });
        // wrap that in a div and extract the contents as a string
        return "[" + $('<div>').append(a).html() + "]";
    },

    domObjectChanged: function(evt) {
        // make sure this is a checkbox
        if (evt.target.nodeName != 'INPUT') {
            return;
        }

        // figure out the id
        var dom_id = evt.target.id;
        var id = /device-(\d+)/.exec(dom_id)[1];
        if (id == '') {
            return;
        }

        // get the checked status
        var checked = this.$('#' + dom_id).is(':checked')? true : false;

        var device = window.devices.get(id);
        device.set('selected', checked);
    }
});

// A class to represent each row in a TableView.  Because DataTables only allow strings
// in the cells, there's not much to do here -- all of the action is above.
var TableRowView = Backbone.View.extend({
    initialize: function(args) {
        this.dataTable = args.dataTable;
        this.parentView = args.parentView;

        this.refresh = $.proxy(this, 'refresh');

        this.model.bind('change', this.refresh);
    },

    refresh: function() {
        var self = this;
        var lastcol = self.parentView.columns.length - 1;
        var rownum = this.dataTable.fnGetPosition(this.el);

        $.each(self.parentView.columns, function (i, col) {
            var val = self.model.get(col.id);
            if (val === null) { val = ''; } // translate null to a string
            self.dataTable.fnUpdate(String(val),
                rownum,
                i+1, // 1-based column (column 0 is the hidden id)
                false, // don't redraw
                (i === lastcol)); // but update data structures on last col
        });

        // redraw once, now that everything is updated
        self.dataTable.fnDraw(false);
    },
});

var ActionButtonView = Backbone.View.extend({
    initialize: function() {
        _.bindAll(this, 'refreshButtonStatus', 'buttonClicked');
        window.devices.bind('change', this.refreshButtonStatus);
    },

    events: {
        'click': 'buttonClicked'
    },

    render: function() {
        this.refreshButtonStatus();
    },

    refreshButtonStatus: function() {
        // only enable the button if at least one device is selected
        var any_selected = false;
        window.devices.each(function (b) {
            any_selected = any_selected ? true : b.get('selected');
        });
        this.$el.attr('disabled', !any_selected);
    },

    buttonClicked: function() {
        // subclasses override this
    }
});

var BmmPowerCycleButtonView = ActionButtonView.extend({
    buttonClicked: function() {
        var selected_pxe_config = window.selected_pxe_config.get('name');
        window.devices.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    device: b,
                    job_type: 'bmm-power-cycle',
                    job_args: { pxe_config: selected_pxe_config, config: {} }
                });
                b.set('selected', false);
            }
        });
    }
});

var LifeguardPowerCycleButtonView = ActionButtonView.extend({
    buttonClicked: function() {
        var selected_pxe_config = window.selected_pxe_config.get('name');
        window.devices.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    device: b,
                    job_type: 'lifeguard-power-cycle',
                    job_args: { }
                });
                b.set('selected', false);
            }
        });
    }
});

var LifeguardPxeBootButtonView = ActionButtonView.extend({
    buttonClicked: function() {
        var selected_pxe_config = window.selected_pxe_config.get('name');
        window.devices.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    device: b,
                    job_type: 'lifeguard-pxe-boot',
                    job_args: { pxe_config: selected_pxe_config, boot_config: {} }
                });
                b.set('selected', false);
            }
        });
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
    },
});
