/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

function show_error(errmsg) {
    $('#error').append('\n' + errmsg).show();
}

function load_and_fetch(name, class_name, next) {
    var model = eval('new ' + class_name + '()');
    model.fetch({
        add: true,
        success: next,
        error: function(jqxhr, response) {
            show_error('AJAX Error while fetching ' + name + ': ' + response.statusText);
        }
    });
    window[name] = model;
}

function setup_ui(next) {
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
        '/ui/js/models.js',
        '/ui/js/views-tables.js',
        '/ui/js/views-toolbar.js',
        '/ui/js/views-controls.js',
        '/ui/js/views-header.js',
        '/ui/js/views-logfiles.js',
        '/ui/js/controllers.js')
    .thenRun(next)
}
