# https://github.com/dw/mitogen/issues/297

from __future__ import (absolute_import, division, print_function)

import os

class VarsModule(object):
    def __init__(self, *args):
        os.environ['EVIL_VARS_PLUGIN'] = 'YIPEEE'

    def get_vars(self, loader, path, entities, cache=True):
        return {}
