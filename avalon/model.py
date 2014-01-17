# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

import greenlet

from greenlet import greenlet as Greenlet
from motor import MotorClient
from pymongo import uri_parser
from pymongo.errors import ConfigurationError
from tornado.ioloop import PeriodicCallback


def defer(f, *args, **kwargs):
    result = []
    main = greenlet.getcurrent().parent
    assert main, 'Not in a child greenlet'

    def callback(res, err):
        if err:
            raise err
        result[:] = [res]
        gr.switch(done=True)

    def deferred(done=False):
        f(callback=callback, *args, **kwargs)
        while not main.switch():
            pass

    gr = Greenlet(deferred)
    gr.switch()
    return result[0]


class Store(object):
    KEEP_ALIVE_TIMEOUT = 60

    def __init__(self):
        self.client = None
        self.collections = []

    def connect(self, uri, db=None, **options):
        io_loop = options.get('io_loop', None)

        self.client = MotorClient(uri, **options).open_sync()

        db = db or uri_parser.parse_uri(uri)['database']
        if not db:
            raise ConfigurationError('No database defined in uri')
        self.db = self.client[db]

        #PeriodicCallback(self.client.alive, Store.KEEP_ALIVE_TIMEOUT,
        #                 io_loop=io_loop).start()

    def __getattr__(self, name):
        c = Collection(model, name)
        self.collections.append(c)
        return c


class Collection(object):
    def __init__(self, model, name):
        self.model = model
        self.name = name

    def insert(self, **attrs):
        return defer(self.model.db[self.name].insert, attrs)

    def find(self, **attrs):
        return defer(self.model.db[self.name].find, attrs)

    def __getattr__(self):
        pass

    def __len__(self):
        return defer(self.model.db[self.name].count)

    def __nonzero__(self):
        return bool(len(self))


class Model(object):
    pass


model = Store()
