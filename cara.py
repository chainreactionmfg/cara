#!/usr/bin/env python3
import collections
import enum
import functools
import sys

import records

MARKER = records.Record('ObjectMarker', ['name'])
AnnotatedRecord = records.Record('AnnotatedRecord', [], {'annotations': list})
Field = records.Record('Field', ['id', 'name', 'type'], {'annotations': list})
Method = records.Record(
    'Method', ['id', 'name', 'params', 'results'], {'annotations': list})
Param = records.Record('Param', ['id', 'name', 'type'], {'annotations': list})


class BuiltinType(object):
    """A builtin type.

    This just passes back the original value, untouched. Some type-checking
    could be done, but I'm lazy.
    """

    def __new__(self, val):
        # If self.checker fails, then the value was invalid, but only bother in
        # debugging mode.
        # self.checker(val)
        return val

# Builtin types are just that, the types, so no need to wrap them. Only keep a
# mapping to base classes and conversion functions in debug mode.
BUILTIN_TYPES = {
    'Int8': int, 'Int16': int, 'Int32': int, 'Int64': int, 'Uint8': int,
    'Uint16': int, 'Uint32': int, 'Uint64': int, 'Float32': float,
    'Float64': float, 'Text': str, 'Data': bytes,
}

mod = sys.modules[__name__]
for name, checker in BUILTIN_TYPES.items():
    setattr(mod, name, type(name, (BuiltinType,), {'checker': checker}))

# Complex types, like Struct, List, and Interface, should know about their
# members and wrap them accordingly. Interface is either a LocalInterface or a
# RemoteInterface, depending on how it was constructed (from python = Local,
# deserialized = Remote)
AnnotationValue = records.Record('AnnotationValue', ['annotation', 'value'])


class Annotation(records.Record('Annotation', ['type', 'name', 'applies_to'],
                                {'annotations': list})):
  ALL = MARKER('*')
  __call__ = lambda s, val: AnnotationValue(s, val)


# Enums!
class Enum(enum.Enum):
    def __init__(self, id, name, annotation=None):
        self.schema_name = name
        self.annotation = annotation or ()

# Consts!
Const = records.Record(
    'Const', ['name', 'type', 'value'], {'annotations': list})


# Since we're targetting msgpack, Struct is a dict, but with our special
# metaclass
class StructMeta(type):

  def __new__(meta, name, bases, attrs):
    """Put all Field instances into __fields__."""
    fields = attrs['__fields__'] = {}
    idfields = attrs['__id_fields__'] = {}
    for key, val in list(attrs.items()):
      if isinstance(val, Field):
        fields[key] = val
        idfields[val.id] = val
        del attrs[key]
    return super().__new__(meta, name, bases, attrs)


class Struct(dict, metaclass=StructMeta):
  __slots__ = ()

  @classmethod
  def Create(cls, **kwargs):
    return cls(kwargs)

  def __init__(self, val):
    # val = {id: value} or {key: value}
    keep = {}
    for k, v in val.items():
      if not isinstance(k, int):
        # val's keys are strings, so we're being created, switch to ints
        field = self._get_field_from_name(k)
        keep[field.id] = field.type(v)
      else:
        keep[k] = self._get_field_from_id(k).type(v)
    super().__init__(keep)

  def __setattr__(self, attr, val):
    if attr in type(self).__fields__:
      self[attr] = self._get_field_from_name(attr).type(val)
    elif attr in type(self).__slots__:
      super().__setattr__(attr, val)

  def __getattr__(self, attr):
    return self[attr]

  def __getitem__(self, item):
    if not isinstance(item, int):
      field = self._get_field_from_name(item)
      item = field.id
    return super().__getitem__(item)

  def _get_field_from_id(self, id):
    return type(self).__id_fields__[id]

  def _get_field_from_name(self, name):
    if isinstance(name, bytes):
      name = name.decode('ascii')
    return type(self).__fields__[name]

  def __str__(self):
    data = ', '.join(
        '{}: {}'.format(self._get_field_from_id(key).name, repr(val))
        for key, val in self.items())
    return '%s({%s})' % (type(self).__name__, data)
  __repr__ = __str__


class BaseList(list):
  __slots__ = ()

  @classmethod
  def Create(cls, *args):
    return cls(args)

  def __init__(self, val):
    super().__init__(self.sub_type(v) for v in val)

  def __str__(self):
    return '{}([{}])'.format(type(self).__name__,
                             ', '.join(repr(item) for item in self))
  __repr__ = __str__

  def Get(self, **kwargs):
    """Convenience function for getting an element of a particular type."""
    return next(val for val in self
                if all(val[attr] == kwargs[attr] for attr in kwargs.keys()))


@functools.lru_cache(maxsize=None)
def List(sub_type):
    return type(
        'List<%s>' % sub_type.__name__, (BaseList,), {'sub_type': sub_type})


# Interface is either a LocalInterface or a RemoteInterface, depending on how
# it was constructed (from python = Local, deserialized = Remote)
class InterfaceMeta(type):

  def __new__(meta, name, bases, attrs):
    """Put all Method instances into __methods__."""
    methods = attrs['__methods__'] = {}
    id_methods = attrs['__id_methods__'] = {}
    for key, val in list(attrs.items()):
      if isinstance(val, Method):
        methods[key] = val
        id_methods[val.id] = key
        del attrs[key]
    return super().__new__(meta, name, bases, attrs)

RemoteInterfaceDescriptor = records.Record(
    'RemoteInterfaceDescriptor', ['remote_id', 'client'])


class Interface(metaclass=InterfaceMeta):

  def __new__(cls, value):
    if isinstance(value, cls):
      return value
    if isinstance(value, RemoteInterfaceDescriptor):
      return RemoteInterface(
          value.remote_id, value.client, cls.__methods__, cls.__id_methods__)
    return super().__new__(cls)

  def __init__(self, value):
    if self is value or isinstance(value, type(self)):
      return
    self._value = value

  def __str__(self):
    return '{}({})'.format(type(self).__name__, self._value)

  def __getitem__(self, key):
      if isinstance(key, int):
          key = self.__id_methods__[key]
      method = self.__methods__.get(key)
      if not method:
          raise KeyError(key)
      return getattr(self._value, key)
  __repr__ = __str__


class RemoteInterface(records.Record(
        'RemoteInterface', ['remote_id', 'client', 'methods', 'id_methods'])):

  def __getattr__(self, attr):
      if isinstance(attr, int):
          attr = self.id_methods[attr]
      method = self.methods.get(attr)
      if method is None:
          raise AttributeError('{} has no attribute {}'.format(self, attr))
          super().__getattr__(attr)

      def ProxyMethod(*args, **kwargs):
          return self.client.registered(self.remote_id, method.id, args, kwargs)
      return ProxyMethod
  __getitem__ = __getattr__


class RemoteInterfaceServer(records.Record('Wrapper', [], {'objs': dict})):

  def registered(self, local_id, method_id, args, kwargs):
    return self.objs[local_id][method_id](*args, **kwargs)

  def register(self, local_id, obj):
    self.objs[local_id] = obj
