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


def bool(obj):
    JSCode('if (obj && obj.__nonzero__) return obj.__nonzero__()')
    return JSCode('Boolean(obj)')


def getattr(obj, name, default_value):
    JSCode('''
    if (obj) {
      if (obj[name] !== undefined) return obj[name];
      if (obj.__getattr__) return obj.__getattr__(obj, name);
    }
    if (default_value === undefined) {
      var objName = obj && obj.__name__;
      throw AttributeError(
        "'" + objName + "' object has no attribute '" + name + "'");
    }
    return default_value;
    ''')


def getitem(obj, key):
    JSCode('if (obj.__getitem__) return obj.__getitem__(key)')
    return JSCode('obj[key]')


def isinstance(obj, cls):
    JSCode('return obj instanceof cls;')


def method(obj, func):
    JSCode('''
    return function() {
      var args = Array.prototype.slice.call(arguments);
      return func.apply(this, [obj].concat(args));
    }
    ''')


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
