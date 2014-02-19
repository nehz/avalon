# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

import logging
import mimetypes
import os
import sys

from bottle import get, default_app, static_file
from bson import json_util as json
from greenlet import greenlet as Greenlet
from six import StringIO
from lxml import html
from lxml.html import builder as E
from sockjs.tornado import router as _router, SockJSRouter
from sockjs.tornado import SockJSConnection as Channel
from tornado.escape import xhtml_unescape as unescape
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application, FallbackHandler
from tornado.wsgi import WSGIContainer

from . import build, client, compiler, _log
from .model import model

_routes = []
_root_path = os.path.dirname(__file__)
_view_path = 'views'
_controller_path = 'controllers'
_cdn = True
_bundle_files = [
    (
        'SockJS',
        '//cdnjs.cloudflare.com/ajax/libs/sockjs-client/0.3.4/sockjs.min.js',
        'sockjs-0.3.4.min.js'
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
        '//ajax.googleapis.com/ajax/libs/angularjs/1.2.6/'
            'angular-animate.min.js',
        'angular-1.2.6/angular-animate.min.js'
    ),
    (
        'angulate',
        'angulate-0.1.0/angulate.js'
    ),
    (
        'avalon',
        'avalon.js'
    )
]
_router.DEFAULT_SETTINGS['sockjs_url'] = '/bundle/sockjs-0.3.4.min.js'

# Fix mimetypes
mimetypes.add_type('image/png', '.png', True)
mimetypes.add_type('audio/mpeg', '.mp3', True)
mimetypes.add_type('application/x-font-ttf', '.ttf', True)
mimetypes.add_type('application/x-font-woff', '.woff', True)


def channel(route):
    def _d(f):
        class _Channel(Channel):
            def on_open(self, request):
                self.request = request
                ip = request.ip
                _log.info('OPEN Channel {0} ({1})'.format(route, ip))

            def on_message(self, message):
                try:
                    Greenlet(f).switch(self, message)
                except Exception as e:
                    _log.exception(e)

            def on_close(self):
                ip = self.request.ip
                _log.info('CLOSE Channel {0} ({1})'.format(route, ip))

        _routes.extend(SockJSRouter(_Channel, route).urls)
        return f
    return _d


@channel('/_avalon')
def _server(request, message):
    message = json.loads(message)
    method = message['method']
    params = message['params']

    if method == 'subscribe':
        model.subscribe(request, *params)

    if method == 'update':
        model[params[0]].update(query=params[1], **params[2])


@get('/')
def _index():
    # Gather, convert and process assets
    DOCTYPE = '<!DOCTYPE html>'
    style = StringIO()
    head = E.HEAD()
    body = E.BODY()
    templates = []
    template_names = []

    def visit(node, f):
        for c in node.getchildren():
            visit(c, f)
            if c.tag != 'template':
                continue
            names = [n[1:] for n in c.keys() if n and n[0] == ':']
            if not names:
                _log.error('Unbound template found (%s)', f)
                continue

            for name in names:
                if name in template_names:
                    _log.error('Duplicate template "%s" found (%s)', name, f)
                    continue

                template = E.SCRIPT(
                    id='template-{0}'.format(name),
                    type='text/x-angulate-template'
                )
                template.text = c.text
                template.extend(c.getchildren())
                templates.append(template)

            template_names.extend(names)
            node.remove(c)
        return

    for dirpath, dirnames, filenames in os.walk(_view_path):
        for filename in filenames:
            ext = os.path.splitext(filename)[-1]
            filename = os.path.join(dirpath, filename)

            handler = build.style_handler.get(ext)
            if handler:
                style.write(handler(filename))
                continue

            handler = build.template_handler.get(ext)
            if not handler:
                continue
            contents = handler(filename)

            if not contents:
                _log.warning('View is empty (%s)', filename)
                continue

            try:
                dom = html.fromstring('<head></head>' + contents)
            except Exception as e:
                _log.error('Parse error (%s) %s', filename, e)
                continue

            for e in dom.getchildren():
                if e.tag == 'head':
                    head.extend(e.getchildren())
                elif e.tag == 'body':
                    visit(e, filename)
                    body.text = (body.text or '') + (e.text or '')
                    body.extend(e.getchildren())
                else:
                    _log.error('View is invalid (%s)', filename)
                    continue

            s = 'angulate.registerTemplate("{0}", "{1}");'
            templates.append(
                E.SCRIPT(
                    '\n'.join([
                        s.format(name, 'template-{0}'.format(name))
                        for name in template_names
                    ]),
                    type='text/javascript'))

    # Append styles
    head.append(E.STYLE(style.getvalue()))

    # Append compiled runtime and Javascript functions
    body.extend([
        E.SCRIPT(
            compiler.runtime(),
            type='text/javascript'),
        E.SCRIPT(
            '\n'.join(f for f in client.compiled()),
            type='text/javascript')
    ])

    # Append bundle
    for b in _bundle_files:
        assert len(b) in [2, 3], 'Invalid bundle file config'
        if len(b) == 2:
            body.append(E.SCRIPT(
                src='bundle/{0}'.format(b[1]),
                type='text/javascript'))
        elif _cdn:
            link = html.tostring(E.SCRIPT(
                src='bundle/{0}'.format(b[2]),
                type='text/javascript'
            ), encoding='utf-8')

            link = link.decode('utf-8').replace('</script>', '<\/script>')
            body.extend([
                E.SCRIPT(
                    src=b[1],
                    type='text/javascript'),
                E.SCRIPT(
                    "window.{0} || document.write('{1}')".format(b[0], link),
                    type='text/javascript')
            ])
        else:
            body.append(E.SCRIPT(
                src='bundle/{0}'.format(b[2]),
                type='text/javascript'))

    # Append templates
    body.extend(templates)

    # Bootstrap angular
    body.append(E.SCRIPT(
        '\n'.join([
            'window._session = {};',
            'window.app = angular.module("app", ["ngAnimate", "angulate"]);',
            'window.app.run(["$rootScope", function($rootScope) {',
            '  $rootScope._session = window._session;',
            '  avalon.scope = $rootScope;'
            '}])',
            'angular.bootstrap(document, ["app"]);'
        ]),
        type='text/javascript'))

    return unescape(html.tostring(E.HTML(head, body), doctype=DOCTYPE,
                                  encoding='utf-8'))


@get('/bundle/<filename:re:(?!\.).+>')
def _bundle(filename):
    return static_file(filename, root=os.path.join(_root_path, 'bundle'))


@get('/<filename:re:(?!\.).+>')
def _static(filename):
    return static_file(filename, root=_view_path)


def serve(db=None, mount_app=None, port=8080, verbose=False,
          view_path=None, controller_path=None, cdn=True):

    global _view_path, _controller_path, _cdn
    _view_path = view_path or _view_path
    _controller_path = controller_path or _controller_path
    _cdn = cdn

    if verbose:
        _log.setLevel(logging.INFO)

    if mount_app:
        r = _routes + [(mount_app[0], FallbackHandler, {
            'fallback': WSGIContainer(mount_app[1])
        })]
    else:
        r = _routes

    # Connect to db
    if db:
        model.connect(db)

    wsgi_app = WSGIContainer(default_app())
    app = Application(r + [
        ('.*', FallbackHandler, {'fallback': wsgi_app})
    ])

    # Import controllers
    module_path = os.path.join(_controller_path, '..')
    if module_path not in sys.path:
        sys.path.append(module_path)

    for dirpath, dirnames, filenames in os.walk(_controller_path):
        for f in filenames:
            module, ext = os.path.splitext(f)
            if ext != '.py':
                continue
            Greenlet(__import__).switch('{0}.{1}'.format(dirpath, module))

    server = HTTPServer(app)
    server.listen(port)
    IOLoop.instance().start()
