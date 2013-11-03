# -*- coding: utf-8 -*-
#==============================================================================
# Name:         server
# Description:  Web sever
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
_static_path = 'static'
_bundle_files = [
    (
        'SockJS',
        '//cdn.sockjs.org/sockjs-0.3.4.min.js',
        'sockjs-0.3.4.min.js'
    ),
    (
        'jQuery',
        '//ajax.googleapis.com/ajax/libs/jquery/1.10.2/jquery.min.js',
        'jquery-1.10.2.min.js'
    ),
    (
        'Handlebars',
        '//cdnjs.cloudflare.com/ajax/libs/handlebars.js/1.0.0/handlebars.min.js',
        'handlebars-1.0.0.min.js'
    ),
    (
        'JSON',
        '//cdnjs.cloudflare.com/ajax/libs/json3/3.2.5/json3.min.js',
        'json3-3.2.5.min.js'
    ),
    (
        'Avalon',
        'avalon.js'
    )
]
_router.DEFAULT_SETTINGS['sockjs_url'] = '/bundle/sockjs-0.3.4.min.js'
_template_handler = {
    '.html': True,
    '.handlebars': True,
    '.hbs': True
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
#======================================================================lo========

@endpoint('/_avalon')
def _server(message):
    print(message)


@get('/')
def _index():
    # Gather and convert all templates into a single handlebars template
    DOCTYPE = '<!DOCTYPE html>'
    head = E.HEAD()
    body = E.BODY()
    templates = []
    template_names = []

    for dirpath, dirnames, filenames in os.walk(_view_path):
        for f in filenames:
            ext = os.path.splitext(f)[-1]

            with open(os.path.join(dirpath, f), 'r', encoding='utf-8') as f:
                t = f.read()

            handler = _template_handler.get(ext, None)
            if not handler:
                continue

            if callable(handler):
                t = handler(t)

            dom = html.fromstring(t)
            for e in dom.getchildren():
                if e.tag == 'head':
                    head.extend(e.getchildren())
                if e.tag == 'body':
                    text = e.text
                    if text:
                        body.append(E.DIV(text))

                    for c in e.getchildren():
                        tail, c.tail = c.tail, None
                        body.append(c)
                        if tail:
                            body.append(E.DIV(tail))

                if e.tag in ['template', 'view']:
                    name = e.get('id') or e.get('name')

                    assert name, \
                        'A template is not named'
                    assert name not in template_names, \
                        'Duplicate template name'

                    template = E.SCRIPT(
                        id=name,
                        type='text/x-handlebars-template'
                    )
                    template.text = e.text
                    template.extend(e.getchildren())

                    templates.append(template)
                    template_names.append(name)

    # Append templates
    body.extend(templates)

    # Append bundle
    for b in _bundle_files:
        assert len(b) in [2, 3], 'Invalid bundle file config'
        if len(b) == 2:
            body.append(E.SCRIPT(
                src='bundle/{0}'.format(b[1]),
                type='text/javascript'
            ))
        else:
            link = html.tostring(E.SCRIPT(
                src='bundle/{0}'.format(b[2]),
                type='text/javascript'
            ), encoding='utf-8').decode('utf-8').replace('</script>', '<\/script>')
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

    # Append compiled Javascript functions
    for j in client._js:
        body.append(E.SCRIPT(
            '{0}; $("{1}").on("{2}", {3})'.format(*j),
            type='text/javascript'
        ))

    return unescape(html.tostring(E.HTML(head, body), doctype=DOCTYPE,
                                  encoding='utf-8'))


@get('/bundle/<filename:re:(?!\.).+>')
def _bundle(filename):
    return static_file(filename, root='{0}/bundle'.format(_root_path))


@get('/<filename:re:(?!\.).+>')
def _static(filename):
    return static_file(filename, root=_static_path)


#==============================================================================
# Helpers
#==============================================================================

def serve(
    mount_app=None, port=8080, verbose=False,
    view_path=None, controller_path=None, static_path=None
):
    # Chdir to app root
    root = inspect.getfile(inspect.currentframe().f_back)
    os.chdir(os.path.dirname(root) or '.')

    global _view_path, _controller_path, _static_path
    _view_path = view_path or _view_path
    _controller_path = controller_path or _controller_path
    _static_path = static_path or _static_path

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
