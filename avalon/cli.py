# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

import os

from argparse import ArgumentParser
from six.moves.configparser import ConfigParser, NoSectionError
from . import server

CONFIG_FILE = 'avalon.conf'


def serve(args):
    config = ConfigParser({'port': '8080', 'db': None})
    config.read([CONFIG_FILE])

    port = int(args.port or int(config.get('app', 'port')))
    view_path = getattr(args, 'view_path', None)
    controller_path = getattr(args, 'controller_path', None)

    if args.cdn is None:
        if config.has_option('app', 'cdn'):
            cdn = config.getboolean('app', 'cdn')
        else:
            cdn = True
    else:
        cdn = args.cdn

    server.serve(db=config.get('app', 'db'), port=port, verbose=args.verbose,
                 view_path=view_path, controller_path=controller_path, cdn=cdn)


def init(args):
    os.mkdir(args.folder)
    os.mkdir(os.path.join(args.folder, 'views'))
    os.mkdir(os.path.join(args.folder, 'controllers'))

    with open(os.path.join(args.folder, CONFIG_FILE), 'w') as f:
        f.write('\n'.join([
            '[app]',
            'view_path = views',
            'controller_path = controllers',
            'port = 8080'
        ]))


def main():
    args = ArgumentParser('avalon')
    command = args.add_subparsers()

    cmd = command.add_parser('init', help='create a project')
    cmd.add_argument('folder', action='store', help='project folder')
    cmd.set_defaults(func=init)

    cmd = command.add_parser('serve', help='serve project')
    cmd.add_argument('-p', dest='port', help='port', default=None)
    cmd.add_argument('--local', dest='cdn', action='store_false',
                     default=None, help='do not use cdn')
    cmd.add_argument('-v', dest='verbose', action='store_true', help='verbose')
    cmd.set_defaults(func=serve)

    args = args.parse_args()
    args.func(args)
