/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { load_model('devices', 'Devices', next); },
        function(next) { load_model('pxe_configs', 'PxeConfigs', next); }
    )
    .thenRun(function(next) {
        // client-side models
        window.selected_pxe_config = new SelectedPxeConfig();
        window.job_queue = new JobQueue();

        // create the required views
        new DeviceTableView({ el: $('#container'), }).render();
        new PxeConfigSelectView({ el: $('#pxe-config'), }).render();
        new BmmPowerCycleButtonView({ el: $('#bmm-power-cycle-button'), }).render();
        new BmmPowerOffButtonView({ el: $('#bmm-power-off-button'), }).render();
        new JobQueueView({ el: $('#job-queue'), }).render();
        new HeaderView({ el: $('#toolbar'), }).render();
        new ToolbarView({ el: $('#toolbar'), }).render();

        // and the job runner
        new JobRunner(window.devices);

        $('#loading').hide();
    });
}
