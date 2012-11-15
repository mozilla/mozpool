function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) {
            var url_info = /[^?]*\?([^=]*)=(.*)/.exec(window.location.href);
            if (!url_info) {
                show_error('Badly formatted URL: expected log.html?device=foo or log.html?request=bar');
                return;
            }
            var object = url_info[1];
            var name = url_info[2];
            window.log = new Log({object: object, name: name});
            window.log.fetch({
                add: true,
                success: next,
                error: function(jqxhr, response) {
                    show_error('AJAX Error while fetching logs: ' + response.statusText);
                }
            });
        }
    )
    .thenRun(function(next) {
        // create the required views
        new LogView({ el: $('#log'), }).render();

        $('#loading').hide();
    })
}


