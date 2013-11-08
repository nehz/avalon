/**
 * Avalon javascript client
 * Copyright: Hybrid Labs
 * License: Private
 */


;(function(global) {
    'use strict';

    var $ = global.jQuery || global.$;
    var template = {};
    var avalon = global.Avalon = {
        context: {_template: template},
        template: template
    };

    /* Model */

    var Observable = avalon.Observable = function() {
        var value;
        var listeners = [];

        //TODO: cleanup listeners
        this.listen = function(f) {
            listeners.push(f);
        };
        this.bind = function(v) {
            value = v;
            $.each(listeners, function(i, f) {
                f(v);
            });
        };
    };

    var Template = avalon.Template = function(name, id) {
        var $template = $('#' + id);
        if (!$template.length) {
            console.error('Template', name, 'not found');
        }

        this.name = name;
        this.render = function(root, context) {
            context = {
                _parent: context,
                _template: template
            };

            root.html($template.html());
            avalon.bootstrap(root, context);
            return context;
        };
    };


    /* Functions */

    var defer = function(f) {
        setTimeout(f, 0);
    };

    var get = function(o, n) {
        n = n.split('.');
        for (var i = 0; i < n.length; i++) {
            o = o[n[i]];
            if (o == undefined) {
                return undefined;
            }
        }
        return o;
    };

    var set = function(o, n, v) {
        n = n.split('.');
        for (var i = 0; i < n.length; i++) {
            if (i < n.length - 1) {
                o = o[n[i]];
            }
            else{
                o[n[i]] = v;
            }
        }
        return v;
    };

    avalon.bootstrap = function(root, context) {
        root = $(root);
        context = context || avalon.context;

        $.each(root.children(), function(i, c) {
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
                avalon.bootstrap(c, context);
                return;
            }

            var o = get(context, bind);
            if (o instanceof Template) {
                // Template bind
                context[o.name] = o.render(root, context);
            }
            else if(!o || o instanceof Observable) {
                if (!o) {
                    o = set(context, bind, new Observable())
                }

                // Input bind
                if ($(c).is('input')) {
                    $(c).on('input keyup blur change', function(e) {
                        if (e.keyCode && e.keyCode != 8) {
                            return;
                        }
                        o.bind($(c).val());
                    });
                    $(c).on('cut', function() {
                        defer(function() {
                            o.bind($(c).val());
                        });
                    });
                    o.listen(function(v) {
                        $(c).val(v);
                    });
                }
                else {
                    if (context[bind] instanceof Array) {
                        // TODO
                    }
                    o.listen(function(v) {
                        if (v instanceof Array) {
                            console.log('repeat');
                        }
                        else {
                            $(c).text(v);
                        }
                    });
                }
            }
            else {
                defer(function() {
                    console.error('Unable to bind', ':' + bind,
                        get(context, bind));
                })
            }
        });
    };


    /* Load */

    $(function() {
        avalon.bootstrap($('#avalon-root'));
    });

    return avalon;
})(window);
