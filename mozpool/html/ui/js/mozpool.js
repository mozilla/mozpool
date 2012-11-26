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
        window.current_renew_duration = new CurrentRenewDuration();
        //window.current_b2gbase = new CurrentB2gBase();
        window.job_queue = new JobQueue();
        window.job_queue.model = RequestJob;

        // create the required views
        new RequestTableView({ el: $('#container'), }).render();
        new IncludeClosedCheckboxView({ el: $('#include-closed-checkbox') }).render();
        new MozpoolCloseRequestsButtonView({ el: $('#close-requests-button') }).render();
        new MozpoolRenewRequestsButtonView({ el: $('#renew-requests-button') }).render();
        //new B2gBaseView({ el: $('#boot-config-b2gbase'), }).render();
        new RenewDurationView({ el: $('#renew-requests-duration') }).render();

        new JobQueueView({ el: $('#job-queue'), }).render();

        // and the job runner
        new JobRunner(window.requests);

        $('#loading').hide();
    });
};
