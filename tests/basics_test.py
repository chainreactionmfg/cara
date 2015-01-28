import unittest

import cara
from tests.basics_capnp import Basic


class BasicsTest(unittest.TestCase):
    def test_field_exists(self):
        assert 'field' in Basic.__fields__
        assert Basic.__fields__['field'].type == cara.Int32

    def test_struct_creation(self):
        assert str(Basic({0: 1})) == 'Basic({field: 1})'
        assert str(Basic({'field': 1})) == 'Basic({field: 1})'
        assert str(Basic({b'field': 1})) == 'Basic({field: 1})'

    def test_list_methods(self):
        nested = Basic({'list': [Basic({'field': 10})], 'ints': [5]})
        assert nested['list'].Get(field=10).field == 10
        assert str(nested['ints']) == 'List[Int32]([5])'
