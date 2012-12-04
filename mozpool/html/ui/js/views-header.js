/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/*
 * Header
 */

var HeaderView = Backbone.View.extend({
    tagName: 'div',

    render: function() {
        // make it slightly opaque so we can see any objects hidden behind it
        $('div#header').css('opacity', '.95');

        // and set the body's margin-bottom to the height of the header
        var height = $('#header').height();
        $('body').css('margin-top', height + 'px');
    }
});

var JobQueueView = Backbone.View.extend({
    tagType: 'div',
    initialize: function(args) {
        _.bindAll(this, 'refresh');

        window.job_queue.bind('change', this.refresh);
        window.job_queue.bind('add', this.refresh);
        window.job_queue.bind('remove', this.refresh);
    },

    render: function() {
        this.$el.addClass('job-queue');
        this.$el.css('float', 'right');
        this.qlen = $('<span>');
        this.$el.append(this.qlen);

        this.refresh();
        return this;
    },

    refresh: function() {
        var length = window.job_queue.length;

        if (length == 1) {
            this.qlen.text('1 job queued');
        } else if (!length) {
            this.qlen.text('no jobs queued');
        } else {
            this.qlen.text(length + ' jobs queued');
        }
    }
});

