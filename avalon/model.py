# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

import greenlet

from bson import ObjectId, json_util as json
from datetime import datetime
from greenlet import greenlet as Greenlet
from motor import MotorClient
from pymongo import uri_parser
from pymongo.errors import CollectionInvalid, ConfigurationError
from tornado.ioloop import PeriodicCallback

from . import _log


class Store(object):
    KEEP_ALIVE_TIMEOUT = 60  # Seconds
    OPSLOG_SIZE = 1000000  # 1 MB

    def __init__(self):
        self.client = None
        self.db = None
        self.subscriptions = {}

    def connect(self, uri, db=None, w=1, j=True, **options):
        io_loop = options.get('io_loop', None)

        self.client = MotorClient(uri, w=w, j=j, **options).open_sync()
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

    def _monitor(self, collection, query_key, query):
        # TODO: Handle doc removal
        # TODO: Batch requests
        try:
            query = {'doc.{0}'.format(k): v for k, v in query.items()}
            query['_id'] = {'$gt': ObjectId.from_datetime(datetime.utcnow())}
            opslog = self.opslog(collection)
            cursor = opslog.find(query, tailable=True, await_data=True)
            item = tail(cursor.tail)
            while True:
                ops, err = next(item)
                if err:
                    raise err

                print(ops)
                if not ops['doc'].get('_id'):
                    _log.warn('Opslog for collection "{0}" contains a '
                              'document with no _id'.format(collection))
                    continue

                if ops['op'] == 'insert':
                    doc = ops['doc']
                elif ops['op'] == 'update':
                    doc = ops['updated']

                response = json.dumps({
                    'response': 'subscribe',
                    'query': query_key,
                    'collection': collection,
                    'result': [doc],
                })

                for request in list(self.subscriptions[query_key]):
                    if request.is_closed:
                        self.subscriptions[query_key].remove(request)
                        continue
                    request.send(response)

                if not self.subscriptions[query_key]:
                    break
        except Exception as e:
            _log.exception(e)
        finally:
            if query_key in self.subscriptions:
                del self.subscriptions[query_key]

    def subscribe(self, request, collection, query_key):
        # TODO: Inject security policies/adapters/transforms here
        query = json.loads(query_key)

        if query_key in self.subscriptions:
            self.subscriptions[query_key].add(request)
        else:
            Greenlet(self._monitor).switch(collection, query_key, query)
            self.subscriptions[query_key] = {request}

        docs = defer(self.db[collection].find(query).to_list, 1000)
        request.send(json.dumps({
            'response': 'subscribe',
            'query': query_key,
            'collection': collection,
            'result': docs
        }))

    def __getattr__(self, name):
        return self[name]

    def __getitem__(self, name):
        return Collection(model, name)


class Collection(object):
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def insert(self, **doc):
        defer(self.store.db[self.name].insert, doc)
        opslog = self.store.opslog(self.name)
        defer(opslog.insert, {'op': 'insert', 'doc': doc}, manipulate=False)

    def update(self, _id=None, query=None, **ops):
        if not ops:
            return
        query = query or _id and {'_id': ObjectId(_id)}
        docs = defer(self.store.db[self.name].find(query).to_list)
        updated = {}
        for d in docs:
            res = defer(self.store.db[self.name].find_and_modify,
                        query, ops, new=True)
            updated[d['_id']] = res

        opslog = self.store.opslog(self.name)
        defer(opslog.insert, [
            {'op': 'update', 'doc': d, 'updated': updated[d['_id']]}
            for d in docs if updated[d['_id']]
        ], manipulate=False)

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


def context():
    gr = greenlet.getcurrent()
    main = greenlet.getcurrent().parent
    assert main is not None, 'Not in a child greenlet'
    return gr, main


def defer(f, *args, **kwargs):
    result = []
    gr, main = context()

    def callback(*r):
        result[:] = r
        gr.switch(True)

    f(callback=callback, *args, **kwargs)
    while not main.switch():
        pass

    res, err = result
    if err:
        raise err
    return res


def tail(f, *args, **kwargs):
    result = []
    gr, main = context()

    def iterator():
        while True:
            while not main.switch():
                pass
            yield result

    def callback(*r):
        result[:] = r
        gr.switch(True)

    f(callback=callback, *args, **kwargs)
    return iterator()


model = Store()
