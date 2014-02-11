# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

"""
Built-in functions
"""

from .compiler import JSCode


def getattr(obj, name, default_):
    JSCode('return obj[name] || '
           'obj.__getattr__ && obj.__getattr__(obj, name) || default_;')


def range(start, stop, step):
    if not stop:
        stop = start
        start = 0
    step = step or 1
    while start < stop:
        yield start
        start += step
