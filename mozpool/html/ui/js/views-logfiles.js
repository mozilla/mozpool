/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

/*
 * Logfiles
 */

var LogView = Backbone.View.extend({
    tagName: 'pre',
    initialize: function(args) {
        _.bindAll(this, 'render', 'addRow', 'scrollToBottom');
        this.scrollToBottom = _.debounce(this.scrollToBottom, 100);

        // note that we ignore "remove" events, so such rows will be deleted from
        // the model but stay in the DOM
        window.log.bind('add', this.addRow);
    },

    render: function() {

        window.log.each(function(l, idx) {
            this.addRow(l);
        }, this);

        return this;
    },

    addRow: function(l) {
        var self = this;
        var line;

        var span;
        var line = $('<div>');
        //line.attr('class', (idx % 2)? 'odd' : 'even');
        self.$el.append(line);

        span = $('<span>')
        span.attr('class', 'timestamp');
        span.text(l.get('timestamp'));
        line.append(span);
        line.append(' ');

        span = $('<span>')
        span.attr('class', 'source');
        span.text(l.get('source'));
        line.append(span);
        line.append(' ');

        span = $('<span>')
        span.attr('class', 'message');
        span.text(l.get('message'));
        line.append(span);

        this.$el.append(line);
        this.scrollToBottom();
    },

    scrollToBottom: function() {
        $('html, body').animate({ scrollTop: $('body').height() }, 700);
    }
});


