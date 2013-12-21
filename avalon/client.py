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


#==============================================================================
# Decorators
#==============================================================================

def expose(f):
    jscompile(f)
    _functions.append(f)
    return f


@attrfunc
def event(name, selector):
    def d(f):
        expose(f)
        return f

    return d


#==============================================================================
# Client helpers
#==============================================================================

@expose
def check(f, args):
    try:
        return f.apply(None, args)
    except:
        return None
