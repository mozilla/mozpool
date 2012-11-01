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
    parse: function(response) {
        return response.boards;
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
    }
});

var JobQueue = Backbone.Collection.extend({
    model: Job
});

