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
            renderFn: "renderLinks" },
    ],

    events: {
        'click input' : 'checkboxClicked',
    },

    initialize: function(args) {
        this.refresh = $.proxy(this, 'refresh');
        this.render = $.proxy(this, 'render');
        _.bindAll(this, 'domObjectChanged', 'checkboxClicked');

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

    renderLinks: function (model) {
        var inv_a = $('<a/>', {
            // TODO get this link from config.ini
            href: 'https://inventory.mozilla.org/en-US/systems/show/' + model.get('inventory_id') + '/',
            text: 'inv'
        });
        var log_a = $('<a/>', {
            href: 'log.html?device=' + model.get('name'),
            text: 'log'
        });
        // for each, wrap in a div and extract the contents as a string
        return "[" + $('<div>').append(log_a).html() + "]"
             + '&nbsp;'
             + "[" + $('<div>').append(inv_a).html() + "]";
    },

    checkboxClicked: function (e) {
        // handle shift-clicking to select a range
        if (e.shiftKey) {
            var target = e.target;

            // the event propagates *after* the state changed, so if this is checked now,
            // that's due to this click
            if (target.checked && this.lastClickedTarget) {
                var from_id, to_id, id_base;
                from_id = parseInt(/.*-(\d+)/.exec(target.id)[1]);
                to_id = parseInt(/.*-(\d+)/.exec(this.lastClickedTarget.id)[1]);
                id_base = /(.*)-\d+/.exec(target.id)[1];

                // sort the two
                if (from_id > to_id) {
                    var t;
                    t = from_id;
                    from_id = to_id;
                    to_id = t;
                }

                // check everything between from and to
                from_id++;
                while (from_id < to_id) {
                    window.devices.get(from_id).set('selected', 1);
                    from_id++;
                }
            }
        } 

        // store the last click for use if the next is with 'shift'
        this.lastClickedTarget = e.target;
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
        window.selected_pxe_config.bind('change', this.refreshButtonStatus);
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

var BmmPowerOffButtonView = ActionButtonView.extend({
    buttonClicked: function() {
        var selected_pxe_config = window.selected_pxe_config.get('name');
        window.devices.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    device: b,
                    job_type: 'bmm-power-off',
                    job_args: {}
                });
                b.set('selected', false);
            }
        });
    }
});

var LifeguardPleaseButtonView = ActionButtonView.extend({
    buttonClicked: function() {
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
        console.log("job args:", job_args);

        window.devices.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    device: b,
                    job_type: job_type,
                    job_args: job_args
                });
                b.set('selected', false);
            }
        });
    },
    refreshButtonStatus: function() {
        // let the parent class handle enable/disable
        ActionButtonView.prototype.refreshButtonStatus.call(this);

        // and change the text based on what's selected
        var selected_pxe_config = window.selected_pxe_config.get('name');
        var button_text = selected_pxe_config ? "PXE Boot" : "Power Cycle";
        this.$el.text(button_text);
    }
});

var LifeguardForceStateButtonView = ActionButtonView.extend({
    buttonClicked: function() {
        var selected_pxe_config = window.selected_pxe_config.get('name');
        window.devices.each(function (b) {
            if (b.get('selected')) {
                job_queue.push({
                    device: b,
                    job_type: 'lifeguard-force-state',
                    job_args: { old_state: b.get('state'), new_state: window.current_force_state.get('state') }
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

var B2gBaseView = Backbone.View.extend({
    initialize: function(args) {
        _.bindAll(this, 'valueChanged');
    },

    events: {
        'change': 'valueChanged'
    },

    valueChanged: function() {
        window.current_b2gbase.set('b2gbase', this.$el.val());
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
            if (!l.get('message')) {
                // for some reason this model ends up with a blank LogLine in it?
                return;
            }
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
