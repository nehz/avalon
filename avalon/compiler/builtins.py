# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

"""
Built-in functions
"""

from .compiler import JSCode
from .exceptions import *


def getattr(obj, name, default_value):
    if JSCode('obj'):
        if JSCode('obj[name] !== undefined'):
            return JSCode('obj[name]')

        if JSCode('obj.__getattr__'):
            return JSCode('obj.__getattr__(obj, name)')

    if JSCode('default_value === undefined'):
        raise AttributeError(obj + " object has no attribute '" + name + "'")
    return default_value


def getitem(obj, key):
    if JSCode('obj.__getitem__'):
        return JSCode('obj.__getitem__(key)')
    return JSCode('obj[key]')


def isinstance(obj, cls):
    JSCode('return obj instanceof cls;')


def method(obj, func):
    return JSCode([
        'function() {',
        '  var args = Array.prototype.slice.call(arguments);',
        '  return func.apply(this, [obj].concat(args)); ',
        '}'
    ])


def range(start, stop, step):
    if not stop:
        stop = start
        start = 0
    step = step or 1
    while start < stop:
        yield start
        start += step


def setattr(obj, name, value):
    if JSCode('obj.__setattr__'):
        return JSCode('obj.__setattr__(obj, name, value)')
    JSCode('obj[name] = value')


def setitem(obj, key, value):
    if JSCode('obj.__setitem__'):
        return JSCode('obj.__setitem__(obj, key, value)')
    JSCode('obj[key] = value')
