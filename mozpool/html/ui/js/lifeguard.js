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
        new TableView({ el: $('#container'), }).render();
        new PxeConfigSelectView({ el: $('#pxe-config'), }).render();
        new LifeguardPowerCycleButtonView({ el: $('#lifeguard-power-cycle-button'), }).render();
        new LifeguardPxeBootButtonView({ el: $('#lifeguard-pxe-boot-button'), }).render();
        new JobQueueView({ el: $('#job-queue'), }).render();

        // and the job runner
        new JobRunner();

        $('#loading').hide();
    })
}

