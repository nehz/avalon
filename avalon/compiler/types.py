# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

"""
Basic types
"""

from .compiler import JSCode
from .exceptions import *


class object(JSCode.Object):
    def toString(self):
        if self.__repr__:
            return self.__repr__()


class generator(object):
    def __init__(self, ctx):
        self.ctx = ctx

    def next(self):
        return self.send(None)

    def send(self, value):
        self.ctx['send'] = value
        self.ctx['func'].call(self.ctx['ctx'], self.ctx)
        if self.ctx['end']:
            raise StopIteration()
        return self.ctx['result']

    def throw(self):
        pass

    def close(self):
        pass

