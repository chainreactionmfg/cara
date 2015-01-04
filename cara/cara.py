#!/usr/bin/env python3
import concurrent.futures
import enum
import functools
import inspect
import keyword
import sys

from crmfg_utils import records

import tornado.concurrent

MARKER = records.Record('ObjectMarker', ['name'])
AnnotationValue = records.Record('AnnotationValue', ['annotation', 'value'])
Method = records.Record(
    'Method', ['id', 'name', 'params', 'results'],
    {'annotations': list})
Param = records.Record('Param', ['id', 'name', 'type'], {'annotations': list})
Enumerant = records.Record(
    'Enumerant', ['name', 'ordinal'], {'annotations': list})


def check_keyword(name):
    if keyword.iskeyword(name):
        return '%s_' % name
    return name


class BuiltinType(object):
    """A builtin type.

    This just passes back the original value, untouched. Some type-checking
    could be done, but I'm lazy.
    """

    def __new__(self, val=None):
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
    'Bool': bool, 'Void': lambda *_: None, 'AnyPointer': None,
}

mod = sys.modules[__name__]
for name, checker in BUILTIN_TYPES.items():
    setattr(mod, name, type(name, (BuiltinType,), {'checker': checker}))


def _ConvertToType(type, value):
  """Convert a value to a field (or param's) type.

  Args:
      type: type to convert to.
      value: value to convert. Can be a Future, in which case we'll chain the
            future into one that returns the converted type.

  Returns:
      Returns either the converted value or a future that will return the
      converted value.
  """
  # XXX: tight-coupling point with pseud (futures)
  if not isinstance(value, (
      tornado.concurrent.Future, concurrent.futures.Future)):
    return type(value)

  new_future = tornado.concurrent.Future()

  def _Done(fut):
      new_future.set_result(_ConvertToType(type, fut.result()))

  value.add_done_callback(_Done)
  # For exceptions only:
  tornado.concurrent.chain_future(value, new_future)
  return new_future


class BaseDeclaration(records.Record(
        'BaseDeclaration', ['name'], {'annotations': list})):

  def FinishDeclaration(self, **kwargs):
    """Called in the generated schema file."""
    for name, val in kwargs.items():
      setattr(self, name, val)
    self.Finished()

  def Finished(self):
    """Called after FinishDeclaration in the generated schema file."""
    pass


class Annotation(BaseDeclaration):
  ALL = MARKER('*')
  optional_attributes = {'type': None, 'applies_to': ALL}

  def __call__(self, val=None):
      return AnnotationValue(self, _ConvertToType(self.type, val))


class Const(BaseDeclaration):
  optional_attributes = {'type': None, 'value': None}

  def Finished(self):
      self.value = _ConvertToType(self.type, self.value)


def Enum(name, enumerants=None):
  return BaseEnum(name, {en.name: en for en in enumerants or []})


class BaseEnum(enum.Enum):
    @classmethod
    def FinishDeclaration(cls, enumerants=None, annotations=None):
        cls.__annotations__ = annotations or []
        # Copy the new enumerant annotations to the proper enumerant.
        enumerants = {en.name: en.annotations for en in enumerants or []}
        for cls_enumerant in cls:
            new_annotations = enumerants[cls_enumerant.name]
            if not new_annotations:
                continue
            cls_enumerant.annotations = new_annotations


def Struct(name):
  return StructMeta(name, (BaseStruct,), {})


# Since we're targetting msgpack, Struct is a dict, but with our special
# metaclass
class StructMeta(type):

  def FinishDeclaration(cls, fields=None, annotations=None):
    """Put all Field instances into __fields__."""
    cls.__annotations__ = annotations or []
    cls_fields = cls.__fields__ = {}
    fields = fields or []
    idfields = cls.__id_fields__ = [None] * len(fields)
    for field in fields:
      cls_fields[field.name] = field
      idfields[field.id] = field


class Field(records.Record(
    'Field', ['id', 'name', 'type'], {'annotations': list, 'default': None})):
    @property
    def default_value(self):
        if self.default is not None:
            return self.default
        if not isinstance(self.type, BaseInterface):
            return self.type()
        # Interfaces have no default value.
        return None


class BaseStruct(dict, metaclass=StructMeta):
  __slots__ = ()

  @classmethod
  def Create(cls, **kwargs):
    return cls(kwargs)

  def __init__(self, val=None):
    # val = {id: value} or {key: value}
    keep = {}
    for k, v in (val or {}).items():
      if not isinstance(k, int):
        # val's keys are strings, so we're being created, switch to ints
        field = self._get_field_from_name(k)
        keep[field.id] = _ConvertToType(field.type, v)
      else:
        keep[k] = _ConvertToType(self._get_field_from_id(k).type, v)
    # the internal dict is a mapping of integer id's to values
    super().__init__(keep)

  def __setattr__(self, attr, val):
    if attr in type(self).__fields__:
      self[attr] = _ConvertToType(self._get_field_from_name(attr).type, val)
    elif attr in type(self).__slots__:
      super().__setattr__(attr, val)

  def __getattr__(self, attr):
    return self[attr]

  def __getitem__(self, item):
    if not isinstance(item, int):
      field = self._get_field_from_name(item)
      item = field.id
    return super().__getitem__(item)

  def __missing__(self, key):
    return type(self).__id_fields__[key].default_value

  def _get_field_from_id(self, id):
    return type(self).__id_fields__[id]

  def _get_field_from_name(self, name):
    if isinstance(name, bytes):
      name = name.decode('ascii')
    return type(self).__fields__[name]

  def __str__(self):
    data = ', '.join(
        '%s: %s' % (self._get_field_from_id(key).name, repr(val))
        for key, val in self.items())
    return '%s({%s})' % (type(self).__name__, data)
  __repr__ = __str__

  def __hash__(self):
    return sum(hash(self[field.id]) for field in type(self).__id_fields__)

  def __eq__(self, other):
    return self is other or (type(self) is type(other) and all(
        self[field.id] == other[field.id]
        for field in type(self).__id_fields__))


class BaseList(list):
  __slots__ = ()

  @classmethod
  def Create(cls, *args):
    return cls(args)

  def __init__(self, val=None):
    super().__init__(self.sub_type(v) for v in (val or []))

  def __str__(self):
    return '%s([%s])' % (type(self).__name__,
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


def Interface(name):
  return InterfaceMeta(name, (BaseInterface,), {})


# Interface is either a LocalInterface or a RemoteInterface, depending on how
# it was constructed (from python = Local, deserialized = Remote)
class InterfaceMeta(type):

  def __init__(cls, name, bases, dct):
    # Interface definition classes don't have __new__ overidden yet anyway.
    cls.__new__ = object.__new__

  def FinishDeclaration(cls, methods=None, superclasses=None, annotations=None):
    """Put all Method instances into __methods__."""
    cls.__annotations__ = annotations or []
    cls_methods = cls.__methods__ = {}
    id_methods = cls.__id_methods__ = {}
    for method in methods or []:
        cls_methods[method.name] = method
        id_methods[method.id] = method.name
    # Lastly, only allow __new__ to be overridden on this particular class.
    cls.__new__ = cls.NewWrapper

  def __getattr__(cls, method_name):
    print(method_name)
    if method_name in cls.__methods__:
      pass

RemoteInterfaceDescriptor = records.Record(
    'RemoteInterfaceDescriptor', ['remote_id', 'client'])


class BaseInterface(metaclass=InterfaceMeta):

  def NewWrapper(cls, value):
    """Potentially creates an instance of cls.

    Here are the situations __new__ would be called:
        * By the framework when converting arguments to a method or elements of
            a struct.
            * Either with a BaseInterface subclass instance:
                struct.attr = Foo()  # FooInterface(Foo()) called
                Foo().method(Foo())  # FooInterface(Foo()) called
            * or with a class or function to be converted/wrapped:
                struct.attr = OtherFoo()  # FooInterface(OtherFoo()) -> wrapped
                struct.attr = lambda: ... # FooInterface(function) -> wrapped
            We're __new__ in both cases.
        * By the user on a subclass, which we should ignore. So we're not
            __new__ here.
    """
    if isinstance(value, cls):
      return value
    if isinstance(value, RemoteInterfaceDescriptor):
      # value came over the wire, so allow us to send method calls back.
      return RemoteInterface(
          value.remote_id, value.client, cls.__methods__, cls.__id_methods__)
    result = super().__new__(cls)
    result.__wrapped__ = value
    if len(cls.__methods__) > 1 and inspect.isfunction(value):
      raise TypeError('Interface %s has too many methods to be registered '
                      'with only a function.' % cls)
    return result

  def __getitem__(self, key):
    if isinstance(key, int):
      key = self.__id_methods__[key]
    method = self.__methods__.get(key)
    if not method:
      raise KeyError(key)

    # Allow wrapping an object.
    if hasattr(self, '__wrapped__'):
      obj = self.__wrapped__
    else:
      obj = self
    if inspect.isfunction(obj):
      return self._MethodWrapper(obj, method)
    if obj is self:
        # skip our getattribute when we're a direct subclass.
        func = super().__getattribute__(key)
    elif isinstance(obj, dict):
        # Allow wrapping a dict with functions instead of a class instance.
        func = obj[key]
    else:
        func = getattr(obj, key)
    return self._MethodWrapper(func, method)

  def __getattribute__(self, attr):
    if attr in type(self).__methods__:
        return self[attr]
    return super().__getattribute__(attr)

  @staticmethod
  def _MethodWrapper(func, method):
    def _Wrapper(*args, **kwargs):
      def _GetParam(name, params):
          param = next((param for param in params if param.name == name), None)
          if param is None:
            raise TypeError('Param %s does not exist for method %s' % (
                name, method.name))
          return param
      # Convert input params to proper types first.
      args = (_ConvertToType(param.type, arg)
              for param, arg in zip(method.params, args))
      kwargs = {
          name: _ConvertToType(_GetParam(name, method.params).type, arg)
          for name, arg in kwargs.items()}
      result = func(*args, **kwargs)

      # Convert result to proper types now.
      if len(method.results) == 0:
        return result
      if len(method.results) == 1:
        param = method.results[0]
        if (isinstance(result, dict)
            and len(result) == 1 and param.name in result):
          # Dict with only the one output param was returned, so unbox it.
          result = result[param.name]
        # Return the result unboxed since it's only one parameter.
        return _ConvertToType(param.type, result)

      if ((isinstance(result, (tuple, list))
           and len(method.results) == len(result))
          or inspect.isgenerator(result)):
        # Convert results according to param id. Not the wisest choice, but
        # still valid. Also, generated param lists are sorted.
        return {param.name: _ConvertToType(param.type, res)
                for param, res in zip(method.results, result)}

      if (not isinstance(result, dict)
          or len(result) != len(method.results)):
        raise TypeError('Multiple output parameters for %s requires a list, '
                        'tuple, or dict to be returned with the right number '
                        'of elements (%s given, %d args needed)' % (
                            method.name, result, len(method.results)))

      # The result is solely a dict, so convert them.
      return {param.name: _ConvertToType(param.type, result[param.name])
              for param in method.results}
    return _Wrapper

  def __str__(self):
    if hasattr(self, '__wrapped__'):
        return '%s(%s)' % (type(self).__name__, self.__wrapped__)
    return '%s' % (type(self).__name__)
  __repr__ = __str__


class RemoteInterface(records.Record(
        'RemoteInterface', ['remote_id', 'client', 'methods', 'id_methods'])):

  def __getattr__(self, attr):
      if isinstance(attr, int):
          attr = self.id_methods[attr]
      method = self.methods.get(attr)
      if method is None:
          raise AttributeError('%s has no attribute %s' % (self, attr))
          super().__getattr__(attr)

      def ProxyMethod(*args, **kwargs):
          # XXX: tight-coupling point with pseud (client.registered)
          return self.client.registered(self.remote_id, method.id, args, kwargs)
      return BaseInterface._MethodWrapper(ProxyMethod, method)
  __getitem__ = __getattr__


class Templated(records.Record('Templated', ['type', 'name', 'templates'])):
  pass


class TemplatedMethod(Method):
  optional_attributes = {'templates': list}
