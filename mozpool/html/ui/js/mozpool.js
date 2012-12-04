/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { load_and_fetch('devicenames', 'DeviceNames', next); },
        function(next) { load_and_fetch('environments', 'Environments', next); },
        function(next) { window.requests = new Requests(); window.requests.update(next); }
    )
    .thenRun(function(next) {
        window.control_state = new CurrentControlState();
        window.job_queue = new JobQueue();
        window.job_queue.model = RequestJob;

        // create the required views
        new RequestTableView({ el: $('#container'), }).render();

        // header and toolbar
        new HeaderView({ el: $('#header'), }).render();
        new ToolbarView({
            el: $('#toolbar'),
            subview_classes: [
                MozpoolNewRequestView,
                MozpoolCloseRequestsView,
                MozpoolRenewRequestsView
            ],
        }).render();

        // and the job runner
        new JobRunner(window.requests);

        $('#loading').hide();
    });
};
