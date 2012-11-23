/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { load_model('requests', 'Requests', next); }
    )
    .thenRun(function(next) {
        // client-side models
        window.current_b2gbase = new CurrentB2gBase();
        window.job_queue = new JobQueue();

        // create the required views
        new RequestTableView({ el: $('#container'), }).render();
        new IncludeClosedView({ el: $('#include-closed') }).render();
        new B2gBaseView({ el: $('#boot-config-b2gbase'), }).render();

        new JobQueueView({ el: $('#job-queue'), }).render();

        // and the job runner
        new JobRunner();

        $('#loading').hide();
    });
};

