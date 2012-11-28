/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { load_and_fetch('devicenames', 'DeviceNames', next); },
        function(next) { window.requests = new Requests(); window.requests.update(next); }
    )
    .thenRun(function(next) {
        // client-side models
        // actions for selected devices
        window.current_renew_duration = new CurrentRenewDuration();

        // create new request
        window.selected_requested_device = new SelectedRequestedDevice();
        window.selected_request_action = new SelectedRequestAction();
        window.current_request_assignee = new CurrentRequestAssignee();
        window.current_request_duration = new CurrentRequestDuration();

        // reimage
        window.current_b2gbase = new CurrentB2gBase();

        // jobs
        window.job_queue = new JobQueue();
        window.job_queue.model = RequestJob;

        // create the required views
        new RequestTableView({ el: $('#container'), }).render();

        // actions for selected devices
        new IncludeClosedCheckboxView({ el: $('#include-closed-checkbox') }).render();
        new MozpoolCloseRequestsButtonView({ el: $('#close-requests-button') }).render();
        new MozpoolRenewRequestsButtonView({ el: $('#renew-requests-button') }).render();
        new MozpoolRenewDurationView({ el: $('#renew-requests-duration') }).render();

        // create new request
        new MozpoolRequestedDeviceSelectView({ el: $('#requested-device-select') }).render();
        new MozpoolRequestActionSelectView({ el: $('#request-action-select') }).render();
        new MozpoolRequestAssigneeView({ el: $('#request-assignee') }).render();
        new MozpoolRequestDurationView({ el: $('#request-duration') }).render();
        new MozpoolRequestSubmitButtonView({ el: $('#request-submit-button') }).render();

        // reimage
        new B2gBaseView({ el: $('#boot-config-b2gbase'), }).render();

        // job queue display
        new JobQueueView({ el: $('#job-queue'), }).render();

        // header and toolbar
        new HeaderView({ el: $('#toolbar'), }).render();
        new ToolbarView({ el: $('#toolbar'), }).render();

        // and the job runner
        new JobRunner(window.requests);

        $('#loading').hide();
    });
};
