// NOTE: all top-level models appear as attributes of window, using the
// lower-cased name.  So the Bootimages instance is window.bootimages.

// db-backed models

var Board = Backbone.Model.extend({
    // in addition to all of the attributes from the REST API, this has a
    // 'selected' attribute that is local to the client
    initialize: function(args) {
        this.set('selected', false);
    },
});

var Boards = Backbone.Collection.extend({
    url: '/api/board/list/?details=true',
    model: Board,
    refreshInterval: 30000,

    initialize: function (args) {
        _.bindAll(this, 'update', 'parse');

        // boards automatically update themselves; set up to update
        // TODO: this could be done better with fetch({merge:true}), but that's
        // not in backbone-0.9.2
        window.setTimeout(this.update, this.refreshInterval);
    },

    parse: function(response) {
        var self = this;
        var old_ids = self.map(function(b) { return b.get('id'); });
        var new_ids = _.map(response.boards, function (b) { return b.id; });

        // calculate added and removed elements from differences
        _.each(_.difference(old_ids, new_ids), function (id) {
            self.get(id).remove();
        });
        _.each(_.difference(new_ids, old_ids), function (id) {
            var board_attrs = response.boards[_.indexOf(new_ids, id)];
            self.push(new self.model(board_attrs));
        });

        // then any updates to the individual boards that haven't been added or
        // removed
        _.each(_.intersection(new_ids, old_ids), function (id) {
            var board_attrs = response.boards[_.indexOf(new_ids, id)];
            var model = self.get(id);
            model.set(board_attrs);
        });

        // this just instructs the fetch/add to not anything else:
        return []
    },

    update: function() {
        var self = this;
        this.fetch({add: true, complete: function () {
            window.setTimeout(self.update, self.refreshInterval);
        }});

    }
});

var Bootimage = Backbone.Model.extend({
});

var Bootimages = Backbone.Collection.extend({
    url: '/api/bootimage/list/',
    model: Bootimage,
    parse: function(response) {
        return $.map(response.bootimages, function(name, id) { return { name: name, id: id }; });
    }
});

// client-only models

var SelectedBootimage = Backbone.Model.extend({
    // currently-selected boot image in the <select>; name can be '' when no
    // image is selected
    initialize: function (args) {
        this.set('name', '');
    }
});

var Job = Backbone.Model.extend({
    initialize: function (args) {
        this.board = args.board;
        this.set('job_type', args.job_type);
        this.set('job_args', args.job_args);
        this.set('board_name', this.board.get('name'));
    },
});

var JobQueue = Backbone.Collection.extend({
    model: Job
});

