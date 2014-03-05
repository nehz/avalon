# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

from .compiler import JSCode
from .utils import AttrFuncDecorator

_functions = []
_scopes = {}


class ScopeType(type):
    def __new__(mcs, name, bases, classdict):
        assert len(bases) <= 1, 'Multiple inheritance not supported'

        scope = type.__new__(mcs, name, bases, classdict)
        scope_name = getattr(bases[0], 'name', None) if bases else None

        if scope_name:
            assert scope_name not in _scopes, \
                'Scope.{0} already defined'.format(scope_name)

            _scopes[scope_name] = {
                'events': {
                    f_name: f.event
                    for f_name, f in classdict.items()
                    if getattr(f, 'event', None)
                },
                'name': scope_name
            }
            expose(scope)

        return scope


class Scope(object):
    def __getattr__(self, name):
        if name is None:
            return Scope

        scope = ScopeType('Scope.{0}'.format(name), (Scope, ), {
            'name': name
        })
        self.name = name
        return scope


class Session(dict):
    def __getattr__(self, name):
        return self[name]


def expose(obj):
    _functions.append(obj)
    return obj


@AttrFuncDecorator
def event(name, selector=''):
    def d(f):
        f.event = (name, selector)
        return f
    return d


@expose
class Promise(object):
    def __init__(self, _id):
        self._id = _id
        self.result = None
        self.have_result = False
        self.task = None

    def set_result(self, value):
        self.result = value
        self.have_result = True

    def set_task(self, task):
        self.task = task


@expose
def check(f, args):
    try:
        return f.apply(None, args)
    except:
        return None


@expose
def task(g):
    if not isinstance(g, JSCode.generator):
        return

    chain = []
    current = g
    res = None
    while current:
        try:
            res = current.send(res)
        except StopIteration as e:
            res = e.value
            current = chain.pop()
            continue

        if isinstance(res, JSCode.generator):
            chain.append(current)
            current = res
            res = None
            continue

        if hasattr(res, '__iter__'):
            # TODO: use dict comprehension when available
            res = list(res)
            wait = {}
            for i, r in enumerate(res):
                if isinstance(r, Promise):
                    wait[r] = i

            for i in range(len(wait)):
                d = yield
                res[wait[d]] = d.result
            res = wait
            continue

        if isinstance(res, Promise):
            res = yield res


@expose
def schedule(g):
    if isinstance(g, JSCode.generator):
        try:
            t = task(g)
            promise = t.next()
            if isinstance(promise, JSCode.Promise):
                promise.set_task(t)
        except StopIteration:
            pass
    elif isinstance(g, JSCode.Promise) and g.task:
        try:
            promise = g.task.send(g.result)
            if isinstance(promise, JSCode.Promise):
                promise.set_task(g.task)
        except StopIteration:
            pass


def compiled():
    from .compiler import js_compile
    return [js_compile(f) for f in _functions]


template = Scope()
session = Session()
