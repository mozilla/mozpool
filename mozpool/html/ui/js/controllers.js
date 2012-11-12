var JobRunner = function () {
    this.initialize(arguments);
};

$.extend(JobRunner.prototype, {
    initialize: function() {
        _.bindAll(this, 'maybeStartJob', 'jobFinished');
        this.running = null;

        window.job_queue.bind('add', this.maybeStartJob);
    },

    maybeStartJob: function() {
        if (this.running) {
            return;
        }

        if (window.job_queue.length == 0) {
            return;
        }

        // get the job, but don't unqueue it yet
        this.running = window.job_queue.at(0);

        // run the job
        console.log("running", this.running.get('job_type'), 'for', this.running.get('device_name'));

        var job_type = this.running.get('job_type');
        if (job_type == 'bmm-power-cycle') {
            this.runBmmPowerCycle();
        } else if (job_type == 'lifeguard-power-cycle') {
            this.runLifeguardPowerCycle();
        } else if (job_type == 'lifeguard-pxe-boot') {
            this.runLifeguardPxeBoot();
        } else {
            this.handleError('unknown job type ' + job_type);
            this.jobFinished();
        }
    },

    runBmmPowerCycle: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/power-cycle/';
        var post_params = {};
        if (job_args['pxe_config']) {
            post_params['pxe_config'] = job_args['pxe_config'];
            post_params['boot_config'] = JSON.stringify(job_args['boot_config']);
        }
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runLifeguardPowerCycle: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/event/please_power_cycle/';
        $.ajax(url, {
            type: 'GET',
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    runLifeguardPxeBoot: function() {
        var self = this;

        var job_args = this.running.get('job_args');
        var url = '//' + this.running.get('device').get('imaging_server') + '/api/device/'
            + this.running.get('device_name') + '/event/please_pxe_boot/';
        var post_params = {};
        if (job_args['pxe_config']) {
            post_params['pxe_config'] = job_args['pxe_config'];
            post_params['boot_config'] = JSON.stringify(job_args['boot_config']);
        }
        $.ajax(url, {
            type: 'POST',
            data: JSON.stringify(post_params),
            error: function (jqxhr, textStatus, errorThrown) {
                self.handleError('error from server: ' + textStatus + ' - ' + errorThrown);
            },
            complete: this.jobFinished
        });
    },

    jobFinished: function() {
        this.running = null;
        window.job_queue.shift();
        this.maybeStartJob();
    },

    handleError: function(msg) {
        console.log(msg);
        if (!this.alreadyAlerted) {
            this.alreadyAlerted = true;
            alert("Errors from the server; see the console log (cmd-opt-k)");
        }
    }
});
