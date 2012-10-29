var Board = Backbone.Model.extend({
});

var Boards = Backbone.Collection.extend({
    url: '/api/board/list/?details=true',
    model: Board,
    parse: function(response) {
        // convert the JSON response to a list of objects
        return $.map(response.boards, function(name, idx) { return { name: name, id: idx+100 }; });
    }
});
