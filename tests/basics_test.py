import unittest

import cara
from tests.basics_capnp import Basic, SimpleInterface, SemiAdvanced


class BasicsTest(unittest.TestCase):
    def test_field_exists(self):
        assert 'field' in Basic.__fields__
        assert Basic.__fields__['field'].type == cara.Int32

    def test_struct_creation(self):
        assert str(Basic({0: 1})) == 'Basic({field: 1})'
        assert str(Basic({'0': 1})) == 'Basic({field: 1})'
        assert str(Basic({'field': 1})) == 'Basic({field: 1})'
        assert str(Basic({b'field': 1})) == 'Basic({field: 1})'

    def test_list_methods(self):
        nested = Basic({'list': [
            Basic({'field': 4}),
            Basic({'field': 10}),
        ], 'ints': [5]})
        assert nested['list'].Get(field=10).field == 10
        assert str(nested['ints']) == 'List[Int32]([5])'

    def test_nested_list_get(self):
        nested = Basic({'list': [
            {'nested': {'field': 5}, 'field': 5},
            {'nested': {'field': 10}, 'field': 5},
        ]})
        assert nested.list.Get(field=5, nested__field=10).nested.field == 10

    def test_union(self):
        advanced = SemiAdvanced({'unnamed': 1, 'unionField': b'data'})
        assert len(advanced.keys()) == 1
        advanced.namedGroup.first = 'text'
        advanced.namedUnion.this = 1
        assert advanced.namedGroup.first == 'text'
        assert advanced.namedUnion.this
        assert not advanced.namedUnion.that
        advanced.namedUnion.that = 2
        assert not advanced.namedUnion.this
        assert advanced.namedUnion.that

    def test_interface(self):
        iface = SimpleInterface({
            'structOut': lambda i: Basic.Create(field=i),
            'structIn': lambda struct: struct.field,
            'multipleOut': lambda: {'one': 1, 'two': 2},
        })
        assert iface.structOut(1).field == 1
        assert iface.structIn(Basic.Create(field=2)) == 2
        assert iface.multipleOut()['one'] == 1
        assert iface.multipleOut()['two'] == 2

        iface = SimpleInterface({
            'structOut': lambda input: {'field': input},
            'structIn': lambda struct: {'output': struct.field},
            'multipleOut': lambda: [1, 2],
        })
        assert iface.structOut(input=3).field == 3
        assert iface.structIn({'field': 3}) == 3
        assert iface.multipleOut()['one'] == 1

    def test_inheritance(self):
        class Inherited(SimpleInterface):
          def structIn(self, struct):
            return struct.field
        instance = Inherited()
        assert instance.structIn(Basic.Create(field=3)) == 3
        assert instance.structIn(field=3) == 3

        wrapped = SimpleInterface(instance)
        assert type(wrapped) == SimpleInterface
        assert type(SimpleInterface(wrapped)) == SimpleInterface
        assert SimpleInterface(wrapped) is wrapped

    def test_replace_types(self):
        class BasicReplacement(object):
            pass
        ReplacedInterface = (
            SimpleInterface.ReplaceTypes([(Basic, BasicReplacement)]))
        replaced_params = ReplacedInterface.__methods__['structIn'].params
        replaced_results = ReplacedInterface.__methods__['structOut'].results
        assert replaced_params == BasicReplacement
        assert replaced_results == BasicReplacement
