# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

import greenlet

from bson import ObjectId
from datetime import datetime
from greenlet import greenlet as Greenlet
from motor import MotorClient
from pymongo import uri_parser
from pymongo.errors import CollectionInvalid, ConfigurationError
from tornado.ioloop import PeriodicCallback

from . import _log


def defer(f, *args, **kwargs):
    result = []
    main = greenlet.getcurrent().parent
    assert main is not None, 'Not in a child greenlet'

    def callback(res, err):
        result[:] = [res, err]
        gr.switch(done=True)

    def deferred(done=False):
        f(callback=callback, *args, **kwargs)
        while not main.switch():
            pass

    gr = Greenlet(deferred)
    gr.switch()
    res, err = result
    if err:
        raise err
    return res


def tail(f, *args, **kwargs):
    result = []
    gr = greenlet.getcurrent()
    main = gr.parent
    assert main is not None, 'Not in a child greenlet'

    def iterator(have_result=False):
        while True:
            while not main.switch():
                pass
            yield result

    def callback(res, err):
        result[:] = [res, err]
        gr.switch(have_result=True)

    f(callback=callback, *args, **kwargs)
    return iterator()


class Store(object):
    KEEP_ALIVE_TIMEOUT = 60  # Seconds
    OPSLOG_SIZE = 1000000  # 1 MB

    def __init__(self):
        self.client = None
        self.db = None
        self.subscriptions = {}

    def connect(self, uri, db=None, **options):
        io_loop = options.get('io_loop', None)

        self.client = MotorClient(uri, **options).open_sync()
        self.client_sync = self.client.sync_client()

        db = db or uri_parser.parse_uri(uri)['database']
        if not db:
            raise ConfigurationError('No database defined in uri')
        self.db = self.client[db]
        self.db_sync = self.client_sync[db]

        #PeriodicCallback(self.client.alive, Store.KEEP_ALIVE_TIMEOUT,
        #                 io_loop=io_loop).start()

    def opslog(self, collection):
        collection_opslog = '{0}.opslog'.format(collection)
        try:
            defer(self.db.create_collection, collection_opslog,
                  capped=True, size=Store.OPSLOG_SIZE)

            # Prime opslog as tailable cursors die on empty collections
            defer(self.db[collection_opslog].insert, {})
        except CollectionInvalid:
            pass

        return self.db[collection_opslog]

    def _monitor(self, collection, query):
        key = frozenset(query.items())
        try:
            query = {'doc.{0}'.format(k): v for k, v in key}
            query['_id'] = {'$gt': ObjectId.from_datetime(datetime.utcnow())}
            opslog = self.opslog(collection)
            cursor = opslog.find(query, tailable=True, await_data=True)
            item = tail(cursor.tail)
            while True:
                doc, err = next(item)
                if err:
                    raise err

                print(doc)
                for request in list(self.subscriptions[key]):
                    if request.is_closed:
                        self.subscriptions[key].remove(request)

                if not self.subscriptions[key]:
                    break
        except Exception as e:
            _log.exception(e)
        finally:
            del self.subscriptions[key]

    def monitor(self, collection, query):
        Greenlet(self._monitor).switch(collection, query)

    def subscribe(self, request, collection, query):
        key = frozenset(query.items())
        if key in self.subscriptions:
            self.subscriptions[key].add(request)
        else:
            self.monitor(collection, query)
            self.subscriptions[key] = {request}

    def __getattr__(self, name):
        return Collection(model, name)


class Collection(object):
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def insert(self, **doc):
        res = defer(self.store.db[self.name].insert, doc)
        opslog = self.store.opslog(self.name)
        defer(opslog.insert, {'op': 'insert', 'doc': doc})
        return res

    def remove(self, **query):
        docs = self.find(query)
        res = defer(self.store.db[self.name].remove, query)
        opslog = self.store.opslog(self.name)
        defer(opslog.insert, [{'op': 'remove', 'doc': d} for d in docs])
        return res

    def find(self, **query):
        return defer(self.store.db[self.name].find(query).to_list)

    def __getattr__(self, name):
        return Collection(self.store, '{0}.{1}'.format(self.name, name))

    def __len__(self):
        return defer(self.store.db[self.name].count)

    def __nonzero__(self):
        return bool(len(self))


class Model(object):
    pass


model = Store()
