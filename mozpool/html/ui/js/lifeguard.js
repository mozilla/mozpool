/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { window.devices = new Devices(); window.devices.update(next);  },
        function(next) { load_and_fetch('images', 'Images', next); },
        function(next) { window.please_verbs = new PleaseVerbs(); next(); }
    )
    .thenRun(function(next) {
        window.control_state = new CurrentControlState();
        window.job_queue = new JobQueue();
        window.job_queue.model = DeviceJob;

        // create the required views
        new LifeguardTableView({ el: $('#container'), }).render();
        new HeaderView({ el: $('#toolbar'), }).render();
        new ToolbarView({
            el: $('#toolbar'),
            subview_classes: [
                LifeguardPleaseView,
                LifeguardForceStateView,
                UpdateCommentsView,
            ],
        }).render();

        // and the job runner
        new JobRunner(window.devices);

        $('#loading').hide();
    });
}

