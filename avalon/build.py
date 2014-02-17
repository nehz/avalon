# -*- coding: utf-8 -*-
#==============================================================================
# Copyright:    Hybrid Labs
# Licence:      See LICENSE
#==============================================================================


import os
from codecs import open


def contents(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()


def jade_compile(filename):
    from pyjade import process
    return process(contents(filename), filename)


def scss_compile(filename):
    import scss
    scss.config.LOAD_PATHS = [os.path.dirname(filename)]
    return scss.Scss().compile(scss_file=filename)


template_handler = {
    '.html': contents,
    '.jade': jade_compile
}

style_handler = {
    '.css': contents,
    '.scss': scss_compile
}
