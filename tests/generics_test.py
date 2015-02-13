import unittest

import cara
from tests.generics_test_capnp import GenericStruct, GenericIface


class GenericsTest(unittest.TestCase):

    def test_struct_templates(self):
        struct = GenericStruct[cara.Text]
        field = struct.__fields__['field']
        assert field.type == struct
        instance = struct.Create(
            struct.Create(defaulted="unicorns"))
        assert instance.defaulted == "defaulteds"
        assert instance.field.field == struct()
        assert instance.ToDict(with_field_names=True) == {
            'field': {'defaulted': 'unicorns', 'field': {'field': {}}}
        }
        instance.defaulted = 'rainbows'
        assert instance.ToDict(with_field_names=True) == {
            'field': {'defaulted': 'unicorns', 'field': {'field': {}}},
            'defaulted': 'rainbows'
        }
        instance[b'defaulted'] = 'puppies'
        assert instance.defaulted == 'puppies'
        hashed = hash(instance)
        assert isinstance(hashed, int)

    def test_nested_struct_templates(self):
        struct = GenericStruct[cara.Text]
        assert isinstance(struct.Nongeneric, cara.StructMeta)
        assert struct.Nongeneric.__fields__['templated'].type == cara.Text

    def test_interface_templates(self):
        iface = GenericIface[cara.Text]
        assert isinstance(iface.Nested, cara.BaseTemplated)
        inputs = []
        iface({'normal': lambda a: inputs.append(a)}).normal(1)
        assert inputs[-1] == 1
        instance = iface({'templated': lambda a: inputs.append(a)})
        assert isinstance(
            instance.__methods__['templated'], cara.TemplatedMethod)
        instance.templated[cara.Text]("text")
        assert inputs[-1] == "text"
