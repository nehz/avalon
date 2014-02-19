# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

from .utils import attrfunc

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
                'events': [
                    (f.event[0], f.event[1], f_name)
                    for f_name, f in classdict.items()
                    if getattr(f, 'event', None)
                ],
                'name': scope_name
            }

            scope = type.__new__(mcs, name, bases, classdict)
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


@attrfunc
def event(name, selector=''):
    def d(f):
        f.event = (name, selector)
        return f

    return d


@expose
def check(f, args):
    try:
        return f.apply(None, args)
    except:
        return None


def compiled():
    from .compiler import js_compile
    return [js_compile(f) for f in _functions]


template = Scope()
session = Session()
