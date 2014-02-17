# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================

from functools import partial


class AttrFuncDecorator(object):
    def __init__(self, f):
        self.f = f

    def __getattr__(self, name):
        return partial(self.f, name)

    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)


def attrfunc(f):
    return AttrFuncDecorator(f)
