# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

"""
Built-in exceptions
"""

class Exception(object):
    def __init__(self, message=None):
        self.message = message or ''

    def __repr__(self):
        return self.__name__ + ':' + self.message


class StopIteration(Exception):
    pass


class RuntimeError(Exception):
    pass


class ValueError(Exception):
    pass


class NotImplemented(Exception):
    pass


class TypeError(Exception):
    pass


class AttributeError(Exception):
    pass
