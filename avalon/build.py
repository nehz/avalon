# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================


import os
import six
from io import open


def contents(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()


def jade_compile(filename):
    from pyjade import process
    return process(contents(filename), filename)


def scss_compile(filename):
    from scss import Scss
    scss = Scss(search_paths=[os.path.dirname(filename)])
    if six.PY3:
        return scss.compile(contents(filename))
    else:
        return scss.compile(contents(filename).encode('utf-8')).decode('utf-8')


template_handler = {
    '.html': contents,
    '.jade': jade_compile
}

style_handler = {
    '.css': contents,
    '.scss': scss_compile
}
