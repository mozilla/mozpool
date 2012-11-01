function show_error(errmsg) {
    $('#error').append('\n' + errmsg).show();
}

function model_loader(name) {
    // get the capitalized class name
    var class_name = name.charAt(0).toUpperCase() + name.slice(1);
    return function(next) {
        var model = eval('new ' + class_name + '()');
        model.fetch({
            success: next,
            error: function(jqxhr, response) {
                show_error('AJAX Error while fetching ' + name + ': ' + response.statusText);
            }
        });
        window[name] = model;
    };
}

// load jquery and underscore, prereqs for the next batch
load(
    '//cdnjs.cloudflare.com/ajax/libs/jquery/1.8.2/jquery.min.js',
    '//cdnjs.cloudflare.com/ajax/libs/underscore.js/1.4.2/underscore-min.js')
// load the other libraries we want
.thenLoad(
    '//cdnjs.cloudflare.com/ajax/libs/datatables/1.9.4/jquery.dataTables.min.js',
    '//cdnjs.cloudflare.com/ajax/libs/jqueryui/1.9.0/jquery-ui.min.js',
    '//cdnjs.cloudflare.com/ajax/libs/backbone.js/0.9.2/backbone-min.js')
// load our own code
.thenLoad(
    '/js/models.js',
    '/js/views.js',
    '/js/controllers.js')
// fetch data for our models
.thenRun(
    model_loader('boards'),
    model_loader('bootimages'))
.thenRun(function(next) {
    // client-side models
    window.selected_bootimage = new SelectedBootimage();
    window.job_queue = new JobQueue();

    // create the required views
    new TableView({ el: $('#container'), }).render();
    new BootimageSelectView({ el: $('#reimage-bootimage'), }).render();
    new PowerCycleButtonView({ el: $('#power-cycle-button'), }).render();
    new ReimageButtonView({ el: $('#reimage-button'), }).render();
    new JobQueueView({ el: $('#job-queue'), }).render();

    // and the job runner
    new JobRunner();

    $('#loading').hide();
})
