# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      Private
#==============================================================================

"""
Built-in functions
"""

from .compiler import JSCode


JSCode('''
  function getattr(obj, name, default_) {
    return obj[name] ||
        obj.__getattr__ && obj.__getattr__(obj, name) || default_;
  }
''')
