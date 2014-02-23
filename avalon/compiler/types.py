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
        return JSCode('Object.prototype.toString.call(this)')


class array(object):
    def __init__(self, iterable=None):
        self.array = JSCode('[]')
        if not iterable:
            return

        if JSCode('iterable instanceof Array'):
            self.array = iterable
            return

        for i in iterable:
            self.append(i)

    def __contains__(self, item):
        return JSCode('this.array.indexOf(item) !== -1')

    def __getitem__(self, index):
        return JSCode('this.array[index]')

    def __hash__(self):
        raise TypeError("unhashable type: '" + self.__class__.__name__ + "'")

    def __iter__(self):
        for i in range(self.array.length):
            yield JSCode('this.array[$ctx.local.i]')

    def __len__(self):
        return JSCode('this.array.length')

    def __nonzero__(self):
        return JSCode('this.array.length > 0')

    def __repr__(self):
        return JSCode('JSON.stringify(this.array)')

    def count(self):
        return self.__len__()

    def index(self, item):
        i = JSCode('this.array.indexOf(item)')
        if i == -1:
            raise ValueError(item + ' is not in list')
        return i


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
        raise NotImplemented()

    def close(self):
        raise NotImplemented()


class list(array):
    def __delitem__(self, index):
        JSCode('this.array.splice(index, 1)')

    def __setitem__(self, index, item):
        JSCode('this.array[index] = item')

    def append(self, item):
        JSCode('this.array.push(item)')

    def extend(self, iterable):
        if JSCode('iterable instanceof Array'):
            JSCode('this.array.push.apply(this.array, iterable)')
            return
        for i in iterable:
            self.append(i)

    def insert(self, index, item):
        JSCode('this.array.splice(index, 0, item)')

    def pop(self):
        return JSCode('this.array.pop()')

    def remove(self, item):
        JSCode('this.array.splice(this.index(item), 1)')

    def reverse(self):
        raise NotImplemented()

    def sort(self):
        raise NotImplemented()


class tuple(array):
    pass
