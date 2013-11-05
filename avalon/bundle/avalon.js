/**
 * Avalon javascript client
 * Copyright: Hybrid Labs
 * License: Private
 */


;(function(global) {
    'use strict';

    var $ = global.jQuery || global.$;
    var avalon = global.Avalon = {
        template: {},
        context: {}
    };
    var template = global.Template = avalon.template;

    avalon.domPatch = function(root, elements) {
        var $root = $(root);
        var $elements = $(elements);
        var removed = 0;
        var removeList = [];

        for (var i = 0; i < $elements.length; i++) {
            var children = $root.contents();
            var c = children[i + removed];
            var e = $elements[i];

            if (!c) {
                // New node
                $root.append(e);
            }
            else if(c.nodeName != e.nodeName) {
                // Append before
                if (children.length - removed < $elements.length) {
                    $(c).insertBefore(e);
                }
                else {
                    removeList.push(c);
                    removed++;
                }
                i--;
            }
            else if(e.nodeType == 3) {
                // Text node
                c.data = e.data;
            }
            else {
                // Merge child node
                avalon.domPatch(c, $(e).contents());
            }
        }

        // Remove elements
        var last = $root.contents()[$elements.length + removed - 1];
        $(last).nextAll().remove();
        $.each(removeList, function(i ,v) {
            v.remove();
        });

        if(!$elements.length) {
            $root.empty();
        }
    };

    $(function() {
        var root = $('#avalon-root');
        var rootTemplate = Handlebars.compile(
            $('#template-avalon-root').html()
        );

        avalon.domPatch(root, rootTemplate(avalon.context));
    });

    return avalon;
})(window);
