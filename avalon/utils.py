# -*- coding: utf-8 -*-
#==============================================================================
# Name:         utils
# Description:  
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

from functools import partial


#==============================================================================
# Helpers
#==============================================================================

class AttrFuncDecorator(object):
    def __init__(self, f):
        self.f = f

    def __getattr__(self, name):
        return partial(self.f, name)

    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)


def attrfunc(f):
    return AttrFuncDecorator(f)
