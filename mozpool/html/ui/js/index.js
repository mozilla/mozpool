/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(function(next) {
        $.get('/api/version/',
            function(data) {
                $('#mozpool-version').text(data.version);
            }
        );
    });
};

