/**
 * Avalon javascript client
 * Copyright: Hybrid Labs
 * License: Private
 */


;(function(global) {
    'use strict';

    var $ = global.jQuery || global.$;
    var avalon = global.Avalon = {};
    var template = avalon.template = global.Template = {};

    var context = {};
    $(function() {
        var root = $('#avalon-root');
        var rootTemplate = Handlebars.compile(
            $('#avalon-root-template').html()
        );

        root.html(rootTemplate(context));
    });
})(window);
