/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

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
            window.log = new Log();
            window.log.setupUrl('/api/' + object + '/' + name + '/log/', limit=1000);
            window.log.update(next=next);
        }
    )
    .thenRun(function(next) {
        // create the required views
        new LogView({ el: $('#log'), }).render();

        $('#loading').hide();
    })
}


