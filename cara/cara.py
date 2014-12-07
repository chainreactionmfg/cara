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
Field = records.Record('Field', ['id', 'name', 'type'], {'annotations': list})
Method = records.Record(
    'Method', ['id', 'name', 'input_params', 'output_params'],
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
    'Bool': bool, 'Void': lambda: None,
}

mod = sys.modules[__name__]
for name, checker in BUILTIN_TYPES.items():
    setattr(mod, name, type(name, (BuiltinType,), {'checker': checker}))


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
      return AnnotationValue(self, val)


# Enums!
# class Enum(enum.Enum):
#     def __init__(self, id, name, annotation=None):
#         self.schema_name = name
#         self.annotation = annotation or ()
# class Enum(BaseDeclaration):
#   optional_attributes = {'enumerants': list, 'enum': None}
#
#   def Finished(self):
#     members = enum._EnumDict()
#     for e in self.enumerants:
#         members[e.name] = e
#     self.enum = enum.EnumMeta(self.name, (enum.Enum,), members)


# Consts!
class Const(BaseDeclaration):
  optional_attributes = {'type': None, 'value': None}


class BaseEnum(enum.Enum):
    @classmethod
    def FinishDeclaration(cls, enumerants=None, annotations=None):
        cls.__annotations__ = annotations or []
        for enumerant in enumerants or []:
            cls._member_names_.append(check_keyword(enumerant.name))
            cls._member_map_[check_keyword(enumerant.name)] = enumerant
            try:
                cls._value2member_map_[enumerant] = enumerant.name
            except TypeError:
                pass
            cls._member_type_ = object


def Enum(name):
  members = enum._EnumDict()
  return enum.EnumMeta(name, (BaseEnum,), members)


def Struct(name):
  return StructMeta(name, (BaseStruct,), {})


# Since we're targetting msgpack, Struct is a dict, but with our special
# metaclass
class StructMeta(type):

  def FinishDeclaration(cls, fields=None, annotations=None):
    """Put all Field instances into __fields__."""
    cls.__annotations__ = annotations or []
    cls_fields = cls.__fields__ = {}
    idfields = cls.__id_fields__ = {}
    for field in fields or []:
      cls_fields[field.name] = field
      idfields[field.id] = field


class BaseStruct(dict, metaclass=StructMeta):
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
        '%s: %s' % (self._get_field_from_id(key).name, repr(val))
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

  def __init__(self, wrapped=None):
    if type(self) == BaseInterface:
        # Only wrapping if we're not a subclass.
        return
    if self is wrapped or isinstance(wrapped, type(self)):
      return

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
    # skip our getattribute when we're a direct subclass.
    if obj == self:
        func = super().__getattribute__(key)
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
      def _Convert(param, val):
          # XXX: tight-coupling point with pseud (futures)
          if isinstance(val, (tornado.concurrent.Future, concurrent.futures.Future)):
              new_future = tornado.concurrent.Future()
              def _Done(fut):
                  new_future.set_result(_Convert(param, fut.result()))
              val.add_done_callback(_Done)
              # For exceptions only:
              tornado.concurrent.chain_future(val, new_future)
              return new_future
          return param.type(val)
      def _GetParam(name, params):
          for param in params:
              if param.name == name:
                  return param
          raise TypeError('Param %s does not exist for method %s' % (
              name, method.name))
      # Convert input params to proper types first.
      args = (_Convert(param, arg)
              for param, arg in zip(method.input_params, args))
      kwargs = {name: _Convert(_GetParam(name, method.input_params), arg)
                for name, arg in kwargs.items()}
      result = func(*args, **kwargs)

      # Convert result to proper types now.
      if len(method.output_params) == 0:
        return result
      if len(method.output_params) == 1:
        param = method.output_params[0]
        if (isinstance(result, dict)
            and len(result) == 1 and param.name in result):
          # Dict with only the one output param was returned, so unbox it.
          result = result[param.name]
        # Return the result unboxed since it's only one parameter.
        return _Convert(param, result)

      if ((isinstance(result, (tuple, list))
           and len(method.output_params) == len(result))
          or inspect.isgenerator(result)):
        # Convert results according to param id. Not the wisest choice, but
        # still valid. Also, generated param lists are sorted.
        return {param.name: _Convert(param, res)
                for param, res in zip(method.output_params, result)}

      if (not isinstance(result, dict)
          or len(result) != len(method.output_params)):
        raise TypeError('Multiple output parameters for %s requires a list, '
                        'tuple, or dict to be returned with the right number '
                        'of elements (%s given, %d args needed)' % (
                            method.name, result, len(method.output_params)))

      # The result is solely a dict, so convert them.
      return {param.name: _Convert(param, result[param.name])
              for param in method.output_params}
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
