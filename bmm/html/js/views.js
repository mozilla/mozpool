var TableView = Backbone.View.extend({
    tagName: 'div',
    columns: [
        { id: "name", title: "Name" },
        { id: "fqdn", title: "FQDN" },
        { id: "inventory_id", title: "Inventory" },
        { id: "mac_address", title: "MAC" },
        { id: "imaging_server", title: "Imaging Server" },
        { id: "relay_info", title: "Relay Info" },
    ],

    initialize: function(args) {
        this.refresh = $.proxy(this, 'refresh');
        this.render = $.proxy(this, 'render');

        this.model = window.boards;
        this.model.bind('refresh', this.refresh);
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
        var aoColumns = [ { bVisible: false } ];

        // data columns
        aoColumns = aoColumns.concat(
            this.columns.map(function(col) {
                var rv = { sTitle: col.title, sClass: 'col-' + col.id };
                if (col.renderFn) {
                    rv.bUseRendered = false;
                    rv.fnRender = function(oObj) {
                        var model = self.model.get(oObj.aData[0]);
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
        // TODO: search

        this.dataTable = this.$('table').dataTable(dtArgs);

        this.refresh();

        return this;
    },

    refresh : function (args) {
        var self = this;

        var newData = self.model.map(function(instance_model) {
            // put the model in the hidden column 0
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
            var instance_model = self.model.get(row[0]);
            var view = new TableRowView({
                model: instance_model,
                el: tr,
                dataTable: self.dataTable,
                parentView: self
            });
            view.render();
        });
    }
});

// A class to represent each row in a TableView.
var TableRowView = Backbone.View.extend({
    initialize: function(args) {
        this.dataTable = args.dataTable;
        this.parentView = args.parentView;

        this.refresh = $.proxy(this, 'refresh');

        this.model.bind('change', this.refresh);
    },

    events: {
    },

    render: function() {
        // note that this.el is set by the parent view
        return this;
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

