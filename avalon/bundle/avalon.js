/**
 * Avalon javascript client
 * Copyright: Hybrid Labs
 * License: Private
 */


;(function(global) {
    'use strict';

    var $ = global.jQuery || global.$;
    var avalon = global.Avalon = {
        context: {}
    };


    /* Model */

    var Observable = avalon.Observable = function() {
        var value;
        var listeners = [];

        this.listen = function(f) {
            listeners.push(f);
        };
        this.bind = function(v) {
            value = v;
            $.each(listeners, function(i, f) {
                f(v);
            });
        };
        this.bootstrap = function(root) {
            this.attached = root;
        };
        this.render = function() {
            console.log('render TODO');
        };
    };

    var Template = avalon.Template = function(name) {
        var template = $('#' + name);
        if (!template.length) {
            console.error('Template', name, 'not found');
        }

        this.context = {};
        this.render = function() {
            if (this.attached) {
                this.attached.html(template.html());
            }
        }
    };
    Template.prototype = new Observable();


    /* Functions */

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
            else if(c.nodeName != e.nodeName || c._index != e._index) {
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
                // Merge node
                $(c).attr('class', $(e).attr('class'));
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

    avalon.bootstrap = function (root, context) {
        root = $(root);
        context = context || avalon.context;

        $.each(root.children(), function(i, c) {
            avalon.bootstrap(c);

            // Get binding
            var bind;
            for (var i = 0; i < c.attributes.length; i++) {
                var b = c.attributes[i];
                if (b && b.name && b.name[0] == ':') {
                    if (!bind) {
                        bind = b.name.slice(1);
                    }
                    else {
                        console.error('Extra bindings', b.name, 'found');
                    }
                }
            }
            if (!bind) {
                return;
            }

            if (context[bind] instanceof Template) {
                context[bind].bootstrap(root);
            }
            else {
                var o = context[bind];
                if (!o) {
                    o = context[bind] = new Observable();
                }
                o.bootstrap(root);

                // Input bind
                if ($(c).is('input')) {
                    $(c).on('input keyup blur change', function(e) {
                        if (e.keyCode && e.keyCode != 8) {
                            return;
                        }
                        o.bind($(c).val());
                    });
                    $(c).on('cut', function() {
                        global.setTimeout(function() {
                            o.bind($(c).val());
                        }, 0);
                    });
                    o.listen(function(v) {
                        $(c).val(v);
                    });
                }
                else {
                    o.listen(function(v) {
                        $(c).text(v);
                    });
                }

                context[bind].render();
            }
        });
    };

    avalon.render = function() {

    };


    /* Load */

    $(function() {
        avalon.bootstrap($('#avalon-root'));
    });

    return avalon;
})(window);
