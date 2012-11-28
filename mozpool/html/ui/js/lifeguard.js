/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { window.devices = new Devices(); window.devices.update(next);  },
        function(next) { load_and_fetch('pxe_configs', 'PxeConfigs', next); }
    )
    .thenRun(function(next) {
        // client-side models
        window.selected_pxe_config = new SelectedPxeConfig();
        window.current_b2gbase = new CurrentB2gBase();
        window.current_force_state = new CurrentForceState();
        window.job_queue = new JobQueue();
        window.job_queue.model = DeviceJob;

        // create the required views
        new DeviceTableView({ el: $('#container'), }).render();
        new PxeConfigSelectView({ el: $('#pxe-config'), }).render();
        new B2gBaseView({ el: $('#boot-config-b2gbase'), }).render();
        new ForceStateView({ el: $('#force-state'), }).render();
        new LifeguardPleaseButtonView({ el: $('#lifeguard-please-button'), }).render();
        new LifeguardForceStateButtonView({ el: $('#lifeguard-force-state-button'), }).render();
        new JobQueueView({ el: $('#job-queue'), }).render();
        new HeaderView({ el: $('#toolbar'), }).render();
        new ToolbarView({ el: $('#toolbar'), }).render();

        // and the job runner
        new JobRunner(window.devices);

        $('#loading').hide();
    });
}

