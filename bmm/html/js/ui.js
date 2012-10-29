load(
    '//cdnjs.cloudflare.com/ajax/libs/jquery/1.8.2/jquery.min.js',
    '//cdnjs.cloudflare.com/ajax/libs/underscore.js/1.4.2/underscore-min.js')
.thenLoad(
    '//cdnjs.cloudflare.com/ajax/libs/datatables/1.9.4/jquery.dataTables.min.js',
    '//cdnjs.cloudflare.com/ajax/libs/jqueryui/1.9.0/jquery-ui.min.js',
    '//cdnjs.cloudflare.com/ajax/libs/backbone.js/0.9.2/backbone-min.js')
.thenLoad(
    '/js/models.js',
    '/js/views.js')
.thenRun(function(next) {
    window.boards = new Boards();
    window.boards.fetch({
        success: next,
        error: function(jqxhr, response) {
            // TODO: generalize this for other errors
            $('#error').append('AJAX Error while fetching boards: ' + response.statusText).show();
        }
    });
})
.thenRun(function(next) {
    window.view = new TableView();
    window.view.render();
    $('#container').replaceWith(window.view.el);
})
