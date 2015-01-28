#!/usr/bin/env python3
import concurrent.futures
import copy
import enum
import functools
import inspect
import keyword
import sys

from crmfg_utils import records
from . import list_cache
from . import generics
from .generics import MethodTemplate

import tornado.concurrent

MARKER = records.ImmutableRecord('ObjectMarker', ['name'])
AnnotationValue = records.ImmutableRecord(
    'AnnotationValue', ['annotation', 'value'])
Method = records.ImmutableRecord(
    'Method', ['id', 'name', 'params', 'results'], {'annotations': list})
Param = records.ImmutableRecord(
    'Param', ['id', 'name', 'type'], {'annotations': list})
Enumerant = records.ImmutableRecord(
    'Enumerant', ['name', 'ordinal'], {'annotations': list})


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


class BaseDeclaration(records.ImmutableRecord(
        'BaseDeclaration', ['name'], {'annotations': list})):

  def FinishDeclaration(self, **kwargs):
    """Called in the generated schema file."""
    for name, val in kwargs.items():
      setattr(self, name, val)
    self.Finished()

  def Finished(self):
    """Called after FinishDeclaration in the generated schema file."""
    pass


class BaseSingleTypeDeclaration(BaseDeclaration):
  optional_attributes = {'type': None}

  def WithTemplates(self, template_map):
    for template, type in template_map:
      if template == self.type:
        new_decl = copy.copy(self)
        new_decl.type = type
        return new_decl
    return self


class Annotation(BaseSingleTypeDeclaration):
  ALL = MARKER('*')
  optional_attributes = {'applies_to': ALL}

  def __call__(self, val=None):
    return AnnotationValue(self, _ConvertToType(self.type, val))


class Const(BaseSingleTypeDeclaration):
  optional_attributes = {'value': None}

  def Finished(self):
      self.value = _ConvertToType(self.type, self.value)


def Enum(name, enumerants=None):
  return BaseEnum(name, {en.name: en.ordinal for en in enumerants or []})


class BaseEnum(enum.IntEnum):
  @classmethod
  def FinishDeclaration(cls, enumerants=None, annotations=None):
    cls.__annotations__ = annotations or []
    cls.__enumerant_annotations__ = {
        en.ordinal: en.annotations for en in enumerants or []}

  def annotations(self):
    # Access for annotations off the enum value.
    return type(self).__enumerant_annotations__[self.value]


def NestedCatchingModifier(cls):
  """Catches set/getattr on declarations that can be nested into.

  Sharing these functions between objects and types is not otherwise possible.
  """

  prev_init = cls.__init__
  prev_setattr = cls.__setattr__
  cls.__slots__ = getattr(cls, '__slots__', ()) + ('__nested__',)

  def __init__(cls, *args, **kwargs):
    prev_init(cls, *args, **kwargs)
    cls.__nested__ = {}
  cls.__init__ = __init__

  def __setattr__(cls, attr, val):
    """Catches nested declarations."""
    if (attr in cls.__slots__
        or (attr.startswith('__') and attr.endswith('__'))
        or attr in dir(cls)):
      return prev_setattr(cls, attr, val)
    cls.__nested__[attr] = val
  cls.__setattr__ = __setattr__

  def __getattr__(cls, attr):
    if (attr.startswith('__') and attr.endswith('__')
            or attr not in cls.__nested__):
        raise AttributeError('%s not in %s' % (attr, cls))
    return cls.__nested__[attr]
  cls.__getattr__ = __getattr__
  return cls


class DeclarationMeta(type):

  def ApplyTemplatesToNested(cls, nested, template_map):
    nested = dict(nested)
    for n_name, decl in nested.items():
      nested[n_name] = decl.WithTemplates(template_map)
    cls.__nested__ = nested


def Struct(name):
  return StructMeta(name, (BaseStruct,), {})


# Since we're targetting msgpack, Struct is a dict, but with our special
# metaclass
@NestedCatchingModifier
class StructMeta(DeclarationMeta):
  __slots__ = ()

  def WithTemplates(cls, template_map):
    """We're not templated, but a field or nested type might me."""
    kwargs = {
        'fields': cls.__id_fields__,
        'annotations': cls.__annotations__
    }
    cls.ApplyTemplatesToKwargs(kwargs, template_map)
    if (kwargs['fields'] != cls.__id_fields__
            or kwargs['annotations'] != cls.__annotations__):
        # Something changed, so make a new struct and return that.
        new_decl = Struct(cls.__name__)
        new_decl.FinishDeclaration(**kwargs)
        new_decl.ApplyTemplatesToNested(cls.__nested__, template_map)
        return new_decl
    return cls

  def ApplyTemplatesToKwargs(cls, kwargs, template_map):
    kwargs['fields'] = [
        generics.ReplaceObject(field, template_map)
        for field in kwargs['fields']]

  def FinishDeclaration(cls, fields=None, annotations=None):
    """Put all Field instances into __fields__."""
    cls.__annotations__ = annotations or []
    cls_fields = cls.__fields__ = {}
    fields = fields or []
    idfields = cls.__id_fields__ = [None] * len(fields)
    for field in fields:
      cls_fields[field.name] = field
      idfields[field.id] = field


class Field(records.ImmutableRecord(
    'Field', ['id', 'name', 'type'],
    {'annotations': list, 'default': None})):
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
  def Create(cls, *args, **kwargs):
    for i, arg in enumerate(args):
      name = cls._get_field_from_id(i).name
      if name in kwargs:
        raise ValueError('%s got two values for %s' % (cls.__name__, name))
      kwargs[name] = arg
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
      field = type(self)._get_field_from_name(attr)
      self[field.id] = _ConvertToType(field.type, val)
    else:
      raise AttributeError('Cannot set %s to %s on %s' % (attr, val, self))

  def __getattr__(self, attr):
    return self[attr]

  def __getitem__(self, item):
    if not isinstance(item, int):
      field = self._get_field_from_name(item)
      item = field.id
    return super().__getitem__(item)

  def __setitem__(self, item, val):
    if isinstance(item, bytes):
      item = item.decode('ascii')
    if item in type(self).__fields__:
      field = type(self)._get_field_from_name(item)
      return super().__setitem__(field.id, val)
    elif item < len(type(self).__id_fields__):
      return super().__setitem__(item, val)
    raise KeyError('Key %s does not exist' % item)

  def __missing__(self, key):
    return type(self).__id_fields__[key].default_value

  def ToDict(self, with_field_names=False):
    return {
        # Choose the key based on the argument.
        type(self)._get_field_from_id(k).name
        if with_field_names else
        k:

        # Get a value.
        v.ToDict(with_field_names=with_field_names)
        if isinstance(v, (BaseStruct, BaseInterface)) else v

        for k, v in self.items()
    }

  @classmethod
  def _get_field_from_id(cls, id):
    return cls.__id_fields__[id]

  @classmethod
  def _get_field_from_name(cls, name):
    if isinstance(name, bytes):
      name = name.decode('ascii')
    return cls.__fields__[name]

  def __str__(self):
    data = ', '.join(
        '%s: %s' % (self._get_field_from_id(key).name, repr(val))
        for key, val in self.items())
    return '%s({%s})' % (type(self).__name__, data)
  __repr__ = __str__

  def __hash__(self):
    return sum(
        hash(self[field.id])
        for field in type(self).__id_fields__
        if self[field.id]
    )

  def __eq__(self, other):
    return self is other or (type(self) is type(other) and all(
        self[field.id] == other[field.id]
        for field in type(self).__id_fields__
        if self[field.id] or other[field.id]))


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
    """Convenience function for getting an element of a particular type.

    Only works for lists of Struct type.
    """
    if not issubclass(self.sub_type, BaseStruct):
      raise TypeError('Cannot use Get on a List of non-Struct types.')
    return next(val for val in self
                if all(val[attr] == kwargs[attr] for attr in kwargs.keys()))


__list_cache__ = list_cache.ListCache()


def List(sub_type):
  cached = __list_cache__.get(sub_type, None)
  if cached is not None:
    return cached

  if isinstance(sub_type, BaseTemplated):
    name = sub_type.name
  elif isinstance(sub_type, generics.Templated):
    name = sub_type.cls.name
  else:
    name = sub_type.__name__

  new_type = type(
      'List[%s]' % name, (BaseList,), {'sub_type': sub_type})
  __list_cache__[sub_type] = new_type
  return new_type


def Interface(name):
  return InterfaceMeta(name, (BaseInterface,), {})


# Interface is either a LocalInterface or a RemoteInterface, depending on how
# it was constructed (from python = Local, deserialized = Remote)
@NestedCatchingModifier
class InterfaceMeta(DeclarationMeta):

  def __new__(meta, name, bases, dct):
    # Reset __new__ for all subclasses of the interface declarations. The actual
    # declaration will have __new__ overridden later. For some reason the other
    # arguments have to be torn off or else we get "TypeError: object() takes no
    # parameters".
    dct['__new__'] = lambda cls, *_, **__: object.__new__(cls)
    return super(InterfaceMeta, meta).__new__(meta, name, bases, dct)

  def ApplyTemplatesToKwargs(cls, kwargs, template_map):
    methods = list(kwargs['methods'])
    for i, method in enumerate(methods):
      params = generics.ReplaceMaybeList(method.params, template_map)
      results = generics.ReplaceMaybeList(method.results, template_map)
      # Only copy the method if it's going to change.
      if params is not method.params or results is not method.results:
        method = copy.copy(method)
        method.params = params
        method.results = results
        methods[i] = method
    kwargs['methods'] = methods

  def FinishDeclaration(cls, methods=None, superclasses=None, annotations=None):
    """Put all Method instances into __methods__."""
    cls.__bases__ += tuple(superclasses or ())
    cls.__annotations__ = annotations or []
    cls_methods = cls.__methods__ = {}
    id_methods = cls.__id_methods__ = {}
    for method in methods or []:
      cls_methods[method.name] = method
      id_methods[method.id] = method.name
    # Lastly, only allow __new__ to be overridden on the declaration class.
    cls.__new__ = cls.NewWrapper

RemoteInterfaceDescriptor = records.ImmutableRecord(
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

    if isinstance(method, TemplatedMethod):
      def _Wrapper(*templates):
        return self._WrapMethod(key, method[templates])
      return generics.GetItemWrapper(_Wrapper)
    else:
      return self._WrapMethod(key, method)

  def _WrapMethod(self, key, method):
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
      args = [_ConvertToType(param.type, arg)
              for param, arg in zip(method.params, args)]
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

  def ToDict(self, with_field_names=False):
    return {
        method.name if with_field_names else id: self[id]
        for id, method in type(self).__id_methods__
    }

  def __str__(self):
    if hasattr(self, '__wrapped__'):
        return '%s(%s)' % (type(self).__name__, self.__wrapped__)
    return '%s' % (type(self).__name__)
  __repr__ = __str__


class RemoteInterface(records.ImmutableRecord(
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


@NestedCatchingModifier
class BaseTemplated(BaseDeclaration):
  required_attributes = ('templates',)
  optional_attributes = {
      '__nested__': list, '_finished': False, '__dependent_decls__': list,
      '__cache__': list_cache.ListCache}

  def _str(self, attrs):
    return super()._str(['name'])

  def Template(self, id):
    if id >= len(self.templates):
      raise ValueError('Template %d out of range' % id)
    return generics.Template(self, id)

  def __getitem__(self, template_values):
    template_values = generics.EnsureTuple(template_values)
    template_map = [(self.Template(i), value)
                    for i, value in enumerate(template_values)]
    if any(isinstance(value, generics.Template)
           for value in template_values):
      # Partial templating only.
      return generics.Templated(self, template_map)

    # Full conversions only.
    return self.WithTemplates(template_map)

  def FinishDeclaration(self, **kwargs):
    if self._finished:
      return
    # Mark as finished, then finish all things waiting on this to be finished.
    self._finished = True
    super().FinishDeclaration(**kwargs)
    for decl in self.__dependent_decls__:
      decl(kwargs)

  def WithTemplates(self, template_map):
    # Filter the template_map to what's relevant to us.
    local_tpl_map = [
        (original, final)
        for original, final in template_map
        if original.cls == self
    ]
    if len(local_tpl_map) != len(self.templates):
        if not local_tpl_map:
            # Nothing changed, ignore it all.
            return self
        return generics.Templated(self, template_map)

    new_decl = self.__cache__.get(local_tpl_map, None)
    if new_decl is not None:
      return new_decl

    def LocalFinishDeclaration(kwargs):
      # Update fields and methods first, but only if templated.
      # Use the original non-local-only template_map because it may include more
      # templates that are used by types in fields or nested classes.
      kwargs = dict(kwargs)
      new_decl.ApplyTemplatesToKwargs(kwargs, template_map)
      new_decl.FinishDeclaration(**kwargs)
      new_decl.ApplyTemplatesToNested(self.__nested__, template_map)

    # If not finished, return self.base_type(name) and mark it as needing to be
    # finished when self is finished.
    # new_decl = type(self).base_type(self.name)
    def get_name(type):
        if isinstance(type, generics.Template):
            return str(type.cls)
        return type.name if hasattr(type, 'name') else str(type)
    new_decl = type(self).base_type(name='%s[%s]' % (
        self.name, ', '.join(get_name(type) for _, type in local_tpl_map)))
    new_decl.__nested__ = type('Nested classes are not available yet.', (), {})
    # Put it in the cache early so we can avoid any recursion problems from the
    # ApplyTemplates call in LocalFinishDeclaration
    self.__cache__[local_tpl_map] = new_decl
    if not self._finished:
      self.__dependent_decls__.append(LocalFinishDeclaration)
    else:
      attribs = (set(type(self).optional_attributes.keys())
                 - set(BaseTemplated.optional_attributes.keys()))
      kwargs = {arg: getattr(self, arg) for arg in attribs}
      LocalFinishDeclaration(kwargs)

    return new_decl


class TemplatedStruct(BaseTemplated):
  optional_attributes = {'fields': list}
  base_type = Struct


class TemplatedInterface(BaseTemplated):
  base_type = Interface
  optional_attributes = {'methods': list, 'superclasses': list}


class TemplatedMethod(BaseTemplated):
  required_attributes = tuple(set(Method.required_attributes) - {'name'})
  _finished = True

  def __getitem__(self, template_values):
    template_map = [
        (generics.MethodTemplate(i), value)
        for i, value in enumerate(generics.EnsureTuple(template_values))]
    return self.WithTemplates(template_map)

  def WithTemplates(self, template_map):
    return Method(
        self.id, self.name,
        annotations=generics.ReplaceMaybeList(self.annotations, template_map),
        params=generics.ReplaceMaybeList(self.params, template_map),
        results=generics.ReplaceMaybeList(self.results, template_map))
