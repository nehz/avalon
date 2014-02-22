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
    if JSCode('obj[name] !== undefined'):
        return obj[name]

    if JSCode('obj.__getattr__'):
        return JSCode('obj.__getattr__(obj, name)')

    return default_value


def range(start, stop, step):
    if not stop:
        stop = start
        start = 0
    step = step or 1
    while start < stop:
        yield start
        start += step
