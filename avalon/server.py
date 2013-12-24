# -*- coding: utf-8 -*-
#==============================================================================
# Name:         server
# Description:  Web server
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

import inspect
import logging
import os
import tornado.ioloop
import tornado.httpserver
import tornado.web
import tornado.wsgi
import tornado.web
import tornado.websocket

from bottle import get, default_app, static_file
from codecs import open
from lxml import html
from lxml.html import builder as E
from sockjs.tornado import router as _router, SockJSRouter
from sockjs.tornado import SockJSConnection as Endpoint
from tornado.websocket import WebSocketHandler as WebSocket
from tornado.escape import xhtml_unescape as unescape

from . import client


#==============================================================================
# Vars
#==============================================================================

_routes = []
_logger = logging.getLogger('avalon')
_root_path = os.path.dirname(__file__)
_view_path = 'view'
_controller_path = 'controller'
_cdn = True
_bundle_files = [
    (
        'SockJS',
        '//cdnjs.cloudflare.com/ajax/libs/sockjs-client/0.3.4/sockjs.min.js',
        'sockjs-0.3.4.min.js'
    ),
    (
        'JSON',
        '//cdnjs.cloudflare.com/ajax/libs/json3/3.2.6/json3.min.js',
        'json3-3.2.6.min.js'
    ),
    (
        'jQuery',
        '//ajax.googleapis.com/ajax/libs/jquery/1.10.2/jquery.min.js',
        'jquery-1.10.2/jquery.min.js'
    ),
    (
        'angular',
        '//ajax.googleapis.com/ajax/libs/angularjs/1.2.6/angular.min.js',
        'angular-1.2.6/angular.min.js'
    ),
    (
        'check(angular.module, ["ngAnimate"])',
        '//ajax.googleapis.com/ajax/libs/angularjs/1.2.6/angular-animate.min.js',
        'angular-1.2.6/angular-animate.min.js'
    ),
    (
        'angulate',
        'angulate-0.1.0/angulate.js'
    )
]
_router.DEFAULT_SETTINGS['sockjs_url'] = '/bundle/sockjs-0.3.4.min.js'
_template_handler = {
    '.html': True
}


#==============================================================================
# Decorators
#==============================================================================

def websocket(route):
    def _d(f):
        class _WebSocket(WebSocket):
            def open(self):
                ip = self.request.remote_ip
                _logger.info('OPEN {0} WebSocket ({1})'.format(route, ip))

            def on_message(self, message):
                f(message)

            def on_close(self):
                ip = self.request.remote_ip
                _logger.info('CLOSE {0} WebSocket ({1})'.format(route, ip))

        c = (route, _WebSocket)
        _routes.append(c)
        return c
    return _d


def endpoint(route):
    def _d(f):
        class _Endpoint(Endpoint):
            def on_open(self, request):
                self.request = request
                ip = request.ip
                _logger.info('OPEN {0} Endpoint ({1})'.format(route, ip))

            def on_message(self, message):
                f(message)

            def on_close(self):
                ip = self.request.ip
                _logger.info('CLOSE {0} Endpoint ({1})'.format(route, ip))

        c = SockJSRouter(_Endpoint, route)
        _routes.extend(c.urls)
        return c
    return _d


#==============================================================================
# Server
#==============================================================================

@endpoint('/_avalon')
def _server(message):
    print(message)


@get('/')
def _index():
    # Gather, convert and process assets
    DOCTYPE = '<!DOCTYPE html>'
    style = E.STYLE()
    head = E.HEAD(style)
    body = E.BODY()
    templates = []
    template_names = []

    for dirpath, dirnames, filenames in os.walk(_view_path):
        for filename in filenames:
            ext = os.path.splitext(filename)[-1]
            filename = os.path.join(dirpath, filename)

            with open(filename, 'r', encoding='utf-8') as f:
                t = f.read()

            if ext in ['.css']:
                style.text = (style.text or '') + t
                continue

            handler = _template_handler.get(ext, None)
            if not handler:
                continue

            if callable(handler):
                t = handler(t)

            if not t:
                _logger.warning('View is empty (%s)', filename)
                continue

            try:
                dom = html.fromstring(t)
            except Exception as e:
                _logger.error('Parse error (%s) %s', filename, e)
                continue

            for e in dom.getchildren():
                if e.tag == 'head':
                    head.extend(e.getchildren())
                elif e.tag == 'body':
                    body.text = (body.text or '') + e.text
                    body.extend(e.getchildren())
                elif e.tag in ['template', 'view']:
                    names = [n[1:] for n in e.keys() if n and n[0] == ':']

                    if not names:
                        continue

                    for name in names:
                        if name in template_names:
                            _logger.error('Duplicate template "%s" found (%s)',
                                          name, filename)
                            continue

                        template = E.SCRIPT(
                            id='template-{0}'.format(name),
                            type='text/x-avalon-template'
                        )
                        template.text = e.text
                        template.extend(e.getchildren())
                        templates.append(template)

                    template_names.extend(names)
                else:
                    _logger.error('View is invalid (%s)', filename)
                    continue

            s = 'angulate.registerTemplate("{0}", "{1}")'
            templates.append(
                E.SCRIPT(
                    '\n'.join([
                        s.format(name, 'template-{0}'.format(name))
                        for name in template_names
                    ]),
                    type='text/javascript'
                )
            )

    # Append compiled Javascript functions
    body.append(E.SCRIPT(
        '\n'.join(f for f in client.compiled()),
        type='text/javascript'
    ))

    # Append bundle
    for b in _bundle_files:
        assert len(b) in [2, 3], 'Invalid bundle file config'
        if len(b) == 2:
            body.append(E.SCRIPT(
                src='bundle/{0}'.format(b[1]),
                type='text/javascript'
            ))
        elif _cdn:
            link = html.tostring(E.SCRIPT(
                src='bundle/{0}'.format(b[2]),
                type='text/javascript'
            ), encoding='utf-8')

            link = link.decode('utf-8').replace('</script>', '<\/script>')
            body.extend([
                E.SCRIPT(
                    src=b[1],
                    type='text/javascript'
                ),
                E.SCRIPT(
                    "window.{0} || document.write('{1}')".format(b[0], link),
                    type='text/javascript'
                )
            ])
        else:
            body.append(E.SCRIPT(
                src='bundle/{0}'.format(b[2]),
                type='text/javascript'
            ))

    # Append templates
    body.extend(templates)

    # Bootstrap angular
    body.append(E.SCRIPT(
        '\n'.join([
            'window._session = {}',
            'window.app = angular.module("app", ["ngAnimate", "angulate"])',
            'window.app.run(["$rootScope", function($rootScope) {',
            '  $rootScope._session = window._session',
            '}])',
            'angular.bootstrap(document, ["app"])'
        ]),
        type='text/javascript'
    ))

    return unescape(html.tostring(E.HTML(head, body), doctype=DOCTYPE,
                                  encoding='utf-8'))


@get('/bundle/<filename:re:(?!\.).+>')
def _bundle(filename):
    return static_file(filename, root='{0}/bundle'.format(_root_path))


@get('/<filename:re:(?!\.).+>')
def _static(filename):
    return static_file(filename, root=_view_path)


#==============================================================================
# Helpers
#==============================================================================

def serve(
    mount_app=None, port=8080, verbose=False,
    view_path=None, controller_path=None, cdn=True
):
    # Chdir to app root
    root = inspect.getfile(inspect.currentframe().f_back)
    os.chdir(os.path.dirname(root) or '.')

    global _view_path, _controller_path, _cdn
    _view_path = view_path or _view_path
    _controller_path = controller_path or _controller_path
    _cdn = cdn

    if verbose:
        _logger.setLevel(logging.INFO)

    if mount_app:
        r = _routes + [(mount_app[0], tornado.web.FallbackHandler, {
            'fallback': tornado.wsgi.WSGIContainer(mount_app[1])
        })]
    else:
        r = _routes

    wsgi_app = tornado.wsgi.WSGIContainer(default_app())
    app = tornado.web.Application(r + [
        ('.*', tornado.web.FallbackHandler, {'fallback': wsgi_app})
    ])

    # Import controllers
    for dirpath, dirnames, filenames in os.walk(_controller_path):
        for f in filenames:
            module, ext = os.path.splitext(f)
            if ext != '.py':
                continue
            __import__('{0}.{1}'.format(dirpath, module))

    server = tornado.httpserver.HTTPServer(app)
    server.listen(port)
    tornado.ioloop.IOLoop.instance().start()
