# -*- coding: utf-8 -*-
#==============================================================================
# Name:         client
# Description:  Javascript client integration
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

from .compiler import jscompile
from .utils import attrfunc


#==============================================================================
# Vars
#==============================================================================

_functions = []
_scopes = []


#==============================================================================
# Decorators
#==============================================================================

def expose(obj):
    jscompile(obj)
    _functions.append(obj)
    return obj


@attrfunc
def event(name, selector):
    def d(f):
        f.event = (name, selector)
        return f

    return d


#==============================================================================
# Scope object
#==============================================================================

class ScopeType(type):
    def __new__(mcs, name, bases, classdict):
        scope = type.__new__(mcs, name, bases, classdict)
        if [b for b in bases if getattr(b, 'name', None)]:
            scope = type.__new__(mcs, name, bases, classdict)
            _scopes.append(name)
            expose(scope)

        return scope


class Scope(object):
    def __getattr__(self, name):
        if name is None:
            return Scope

        scope = ScopeType('Scope.{0}'.format(name), (Scope, ), {
            'name': name
        })
        return scope


template = Scope()


#==============================================================================
# Client helpers
#==============================================================================

@expose
def check(f, args):
    try:
        return f.apply(None, args)
    except:
        return None
