# flake8: noqa
"""
Import hierarchy should be such that this is possible:

import cara
cara.Struct(...)

cara.cara_pseud.register_client(...)
"""
from cara import *
import cara_pseud
