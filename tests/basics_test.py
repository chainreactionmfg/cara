import unittest

import cara
from tests.basics_capnp import Basic


class BasicsTest(unittest.TestCase):
    def test_field_exists(self):
        assert 'field' in Basic.__fields__
        assert Basic.__fields__['field'].type == cara.Int32
