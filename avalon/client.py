# -*- coding: utf-8 -*-
#==============================================================================
# Name:         client
# Description:  Javascript client integration
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

from .compiler import jscompile


#==============================================================================
# Vars
#==============================================================================

_js = []


#==============================================================================
# Functions
#==============================================================================

def on(selector, events):
    def _f(f):
        name = '{0}.{1}'.format(f.__module__, f.__name__)
        name = name.split('.', 1)[-1].replace('.', '_')
        _js.append((jscompile(f, name), selector, events, name))
        return f
    return _f
