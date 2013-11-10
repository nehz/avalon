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

    var Observable = avalon.Observable = function(v) {
        var listeners = [];
        this.value = v;

        //TODO: cleanup listeners
        this.listen = function(f) {
            listeners.push(f);
            return f;
        };
        this.bind = function(v) {
            if (v == this.value) {
                return v;
            }

            this.value = v;
            $.each(listeners, function(i, f) {
                f(v);
            });

            return v;
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

            $(root).html($template.html());
            return avalon.bootstrap(root, context);
        };
    };

    var Repeat = avalon.Repeat = function(root, v, context) {
        var $root = $(root);
        var bind = $root.prop('bind');

        var value = v;
        var repeat = [];
        var contexts = context[bind + '_repeat'] = [];

        function create(index) {
            var r = $root.prop('template').clone();
            contexts[index] = avalon.bootstrap(r, {
                _parent: context,
                _template: template,
                _index: new Observable(index)
            });
            return r;
        }

        var last = $root;
        for (var i = 0; i < v.length; i++) {
            var r = create(i);
            repeat.push(r);
            last = r.insertAfter(last);
        }

        this.merge = function(v) {
            if (value == v) {
                return;
            }

            var removed = [];
            var last = $root;

            if (!v.length) {
                removed = value;
            }

            for(var i = 0; i < v.length; i++) {
                if (value.length <= i) {
                    last = create(i).insertAfter(last);
                    repeat.push(last);
                    value.push(v[i]);
                }
                else if(value[i] !== v[i]) {
                    if (value.length <= v.length) {
                        contexts.splice(i, 0, undefined);
                        last = create(i).insertAfter(last);
                        repeat.splice(i, 0, last);
                        value.splice(i, 0, v[i]);
                    }
                    else {
                        last = repeat[i];
                        removed.push(repeat.splice(i, 1)[0]);
                        value.splice(i, 1);
                        contexts.splice(i, 1);
                    }
                }
                else {
                    last = repeat[i];
                }
                contexts[i]._index.bind(i);
            }

            removed.push.apply(
                removed,
                repeat.splice(i, repeat.length)
            );
            value.splice(i, value.length);
            contexts.splice(i, contexts.length);

            for (var i = 0; i < removed.length; i++) {
                removed[i].remove();
            }
        };

        this.destroy = function() {
            // TODO: cleanup child scopes
            for (var i = 0; i < value.length; i++) {
                repeat[i].remove();
            }
            delete context[bind + '_' + i];
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
            if (!o[n[i]]) {
                o[n[i]] = {};
            }
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
        if (context == undefined) {
            console.error('No context supplied for', root);
            return undefined;
        }

        var templateId = 0;
        root = $(root);

        $.each(root.children(), function(i, c) {
            var $c = $(c);
            var leaf = $c.contents().length == 0;
            
            // Get binding
            var bind;
            for (var i = 0; i < c.attributes.length; i++) {
                var b = c.attributes[i];
                if (b && b.name && b.name.charAt(0) == ':') {
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
            if (o == undefined) {
                o = set(context, bind, new Observable())
            }

            if (o instanceof Template) {
                // Template bind
                bind = o.name + '_' + ($c.attr('id') || templateId++);
                context[bind] = o.render(c, context);
            }
            else if(o instanceof Observable) {
                if ($c.is('input')) {
                    // Input bind
                    $c.on('input keypress cut paste show', function() {
                        defer(function() {
                            o.bind($c.val());
                        });
                    });
                    $c.on('keydown keyup', function(e) {
                        if (e.keyCode == 8)  {
                            defer(function() {
                                o.bind($c.val());
                            });
                        }
                    });
                    (o.listen(function(v) {
                        $c.val(v);
                    }))(o.value);
                }
                else {
                    // Display bind
                    $c.prop('template', $c.clone());
                    $c.prop('display', $c.css('display'));
                    $c.prop('bind', bind);

                    if (!o.value) {
                        avalon.bootstrap($c, context);
                    }

                    (o.listen(function(v) {
                        if (!v && !leaf) {
                            $c.css('display', 'none');
                            // TODO: cleanup repeat

                            var repeat = $c.prop('repeat');
                            if (repeat) {
                                $c.removeProp('repeat');
                                repeat.destroy();
                            }
                            return;
                        }

                        // TODO: refactor, also own repeat context (rework)
                        if (v instanceof Array) {
                            $c.css('display', 'none');

                            var repeat = $c.prop('repeat');
                            if (!repeat) {
                                $c.prop('repeat', new Repeat($c, v, context));
                            }
                            else {
                                repeat.merge(v);
                            }
                        }
                        else {
                            $c.css('display', $c.prop('display'));

                            //TODO: clean up code
                            //TODO: repeated code, refactor
                            var repeat = $c.prop('repeat');
                            if (repeat) {
                                $c.removeProp('repeat');
                                repeat.destroy();
                            }

                            // Bind text value if no children
                            if (leaf) {
                                $c.text(v);
                            }
                            else {
                                $c.html($c.prop('template').html());
                                avalon.bootstrap($c, context);
                            }
                        }
                    }))(o.value);
                }
            }
            else if(typeof(o) == 'number' || typeof(o) == 'string') {
                if (leaf) {
                    $c.text(o);
                }
                else {
                    if (o) {
                        avalon.bootstrap($c, context);
                    }
                    else {
                        $c.prop('display', $c.css('display'));
                    }
                }
            }
            else {
                defer(function() {
                    console.error('Unable to bind', ':' + bind,
                        get(context, bind));
                })
            }
        });
        return context;
    };


    /* Load */

    $(function() {
        avalon.bootstrap($('#avalon-root'), avalon.context);
    });

    return avalon;
})(window);
