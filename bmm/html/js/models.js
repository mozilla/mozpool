var Board = Backbone.Model.extend({
});

var Boards = Backbone.Collection.extend({
    url: '/api/board/list/?details=true',
    model: Board,
    parse: function(response) {
        return response.boards;
    }
});
