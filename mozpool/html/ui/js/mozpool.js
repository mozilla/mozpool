function run_ui(next) {
    run(setup_ui)
    // fetch data for our models
    .thenRun(
        function(next) { load_model('devices', 'Devices', next); },
        function(next) { load_model('pxe_configs', 'PxeConfigs', next); }
    )
    .thenRun(function(next) {
        // client-side models
        window.current_b2gbase = new CurrentB2gBase();

        // create the required views
        new TableView({ el: $('#container'), }).render();
        new B2gBaseView({ el: $('#boot-config-b2gbase'), }).render();

        // and the job runner
        new JobRunner();

        $('#loading').hide();
    })
}
