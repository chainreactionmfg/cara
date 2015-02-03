import unittest

from tests.replacing_capnp import Root

class HostReplacement(object):
    def __init__(self, dct):
        obj = Root.Host(dct)
        self.hostname = obj.hostname
        self.port = obj.port

class ReplacingTest(unittest.TestCase):

    def test_replacing(self):
        NewRoot = Root.ReplaceTypes([(Root.Host, HostReplacement)])

    def test_updating_struct(self):
        root = Root(
            {'field': {'subField': {'hostname': 'cara.readthedocs.org'}}})
        NewRoot = Root.ReplaceTypes([(Root.Host, HostReplacement)])
        new_root = NewRoot(root)
        assert root != new_root
        assert isinstance(new_root.field.subField, HostReplacement)
        assert NewRoot.Host is not Root.Host
        assert NewRoot.Host is HostReplacement
