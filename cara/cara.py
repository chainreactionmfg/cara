#!/usr/bin/env python3
import copy
import enum
import inspect
import sys

from crmfg_utils import records
from . import generics
from . import list_cache
from . import type_registry
from .generics import MethodTemplate  # noqa

AnnotationValue = records.ImmutableRecord(
    'AnnotationValue', ['annotation', 'value'])
Method = records.ImmutableRecord(
    'Method', ['id', 'name', 'params', 'results'], {'annotations': list})
Param = records.ImmutableRecord(
    'Param', ['id', 'name', 'type'], {'annotations': list})
Enumerant = records.ImmutableRecord(
    'Enumerant', ['name', 'ordinal'], {'annotations': list})
Group = records.ImmutableRecord(
    'Group', ['id', 'name', 'fields'], {'annotations': list})
Union = records.ImmutableRecord(
    'Union', ['fields'], {'annotations': list})


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


# Registry of base types and functions that take the target type and a value
# that should be converted to that type. The value will be an instance of the
# base type key.
type_conversion_registry = type_registry.TypeRegistry()


def _ConvertToType(type, value):
  """Convert a value to a field (or param's) type.

  Sometimes the value is not converted directly, this can be controlled by
  type_conversion_registry. If the given value is an instance of a type in
  that registry (or a subclass of a type), then conversion will be delegated to
  the function registered with it.

  NOTE: This can't be done through singledispatch because it gets hung up on
  records (the second record class's instance passed in hangs). Once that's
  resolved, we can switch this to singledispatch.

  Args:
    type: type to convert to.
    value: value to convert.

  Returns:
    Either the converted value or whatever a registered function returns.
  """
  if type_conversion_registry.IsInstanceOfAny(value):
    return type_conversion_registry.LookUp(value)(type, value)
  return type(value)


class BaseDeclaration(records.ImmutableRecord(
        'BaseDeclaration', ['name', 'id'], {'annotations': list})):

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

  def ReplaceTypes(self, template_map, memo=None):
    for template, type in template_map:
      if template == self.type:
        new_decl = copy.copy(self)
        new_decl.type = type
        return new_decl
    return self


class Annotation(BaseSingleTypeDeclaration):
  ALL = generics.MARKER('*')
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

  def ApplyTemplatesToNested(cls, nested, template_map, memo=None):
    if isinstance(nested, generics.MARKER):
      return
    nested = dict(nested)
    for n_name, decl in nested.items():
      replacement = generics.ReplaceType(decl, template_map, memo=memo)
      if hasattr(replacement, 'ReplaceTypes'):
          replacement = replacement.ReplaceTypes(template_map, memo=memo)
      nested[n_name] = replacement
    cls.__nested__ = nested


def Struct(name, id):
  return StructMeta(name, (BaseStruct,), {'id': id})


# Since we're targetting msgpack, Struct is a dict, but with our special
# metaclass
@NestedCatchingModifier
class StructMeta(DeclarationMeta):
  __slots__ = ()

  def ReplaceTypes(cls, template_map, memo=None):
    """We're not templated, but a field or nested type might me."""
    if not hasattr(cls, '__fields__'):
      return cls
    kwargs = {
        'fields': cls.__fields__.values(),
        'annotations': cls.__annotations__
    }
    cls.ApplyTemplatesToKwargs(kwargs, template_map, memo=memo)
    new_decl = Struct(cls.__name__, cls.id)
    new_decl.ApplyTemplatesToNested(cls.__nested__, template_map, memo=memo)
    if (kwargs['fields'] != cls.__id_fields__
            or kwargs['annotations'] != cls.__annotations__
            or new_decl.__nested__ != cls.__nested__):
        # Something changed, so return a new struct declaration.
        new_decl.FinishDeclaration(**kwargs)
        return new_decl
    return cls

  def ApplyTemplatesToKwargs(cls, kwargs, template_map, memo=None):
    kwargs['fields'] = [
        generics.ReplaceObject(field, template_map, memo=memo)
        for field in kwargs['fields']]

  def FinishDeclaration(cls, fields=None, annotations=None):
    """Put all Field instances into __fields__."""
    cls.__annotations__ = annotations or []
    fields = fields or []

    # Unions are always the first field.
    cls.__union_fields__ = set()
    if fields and isinstance(fields[0], Union):
        # Store the union field ID's, then act like they don't exist.
        cls.__union_fields__ = {field.id for field in fields[0].fields}
        fields[0:1] = fields[0].fields

    cls_fields = cls.__fields__ = {}
    idfields = cls.__id_fields__ = [None] * len(fields)
    for field in fields:
      if isinstance(field, Group):
        struct = Struct('%s.%s' % (cls.__name__, field.name), cls.id)
        struct.FinishDeclaration(
            fields=field.fields, annotations=field.annotations)
        field = Field(id=field.id, name=field.name, type=struct)
      cls_fields[field.name] = field
      idfields[field.id] = field

  def __eq__(cls, other):
    return cls is other or (
        type(cls) is type(other)
        and len(cls.mro()) == len(other.mro())  # Subclasses
        and hasattr(cls, '__fields__') and hasattr(other, '__fields__')
        and cls.__fields__ == other.__fields__
        and cls.__annotations__ == other.__annotations__)

  def __hash__(cls):
    return object.__hash__(cls)


class Field(records.ImmutableRecord(
    'Field', ['id', 'name', 'type'],
    {'annotations': list, 'default': None})):
  @property
  def default_value(self):
    if self.default is not None:
      return copy.copy(self.default)
    if not issubclass(self.type, (BaseEnum, BaseInterface)):
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
    union_fields = type(self).__union_fields__
    for k, v in (val or {}).items():
      if not isinstance(k, int):
        # val's keys are strings, but we're being created, switch to ints
        if k.isdigit():
          # It was just the ID as a string, switch back to that.
          k = int(k)
          field = self._get_field_from_id(k)
        else:
          field = self._get_field_from_name(k)
          k = field.id
      else:
        field = self._get_field_from_id(k)
      if k in union_fields and union_fields & set(keep.keys()):
        # Remove other union fields.
        for id in union_fields:
          keep.pop(id, None)
      keep[k] = _ConvertToType(field.type, v)
    # the internal dict is a mapping of integer id's to values
    super().__init__(keep)

  def __setattr__(self, attr, val):
    if attr in type(self).__fields__:
      field = type(self)._get_field_from_name(attr)
      return self.__setitem__(field.id, val, field=field)
    else:
      raise AttributeError('Cannot set %s to %s on %s' % (attr, val, self))

  def __getattr__(self, attr):
    return self[attr]

  def __getitem__(self, item):
    if not isinstance(item, int):
      field = self._get_field_from_name(item)
      item = field.id
    return super().__getitem__(item)

  def __setitem__(self, item, val, field=None):
    if isinstance(item, bytes):
      # str -> bytes
      item = item.decode('ascii')
    if item in type(self).__fields__:
      # bytes -> int
      if field is None:
        field = type(self)._get_field_from_name(item)
      item = field.id
    if item < len(type(self).__id_fields__):
      union_fields = type(self).__union_fields__
      if item in union_fields and union_fields & set(self.keys()):
        # Clear the other fields in the union first.
        for id in union_fields:
          self.pop(id, None)
      field = type(self).__id_fields__[item]
      return super().__setitem__(item, _ConvertToType(field.type, val))
    raise KeyError('Key %s does not exist' % item)

  def __missing__(self, key):
    field = type(self).__id_fields__[key]
    ret = field.default_value
    if isinstance(type(ret), DeclarationMeta):
      # Store the result if it's not a builtin that can't change.
      self.__setitem__(key, ret, field=field)
      return self[key]
    return ret

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
    field = cls.__fields__.get(name)
    if field is None:
      raise KeyError('%s has no field named %s' % (cls, name))
    return field

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
    if self is other:
      return True
    if not isinstance(other, type(self)):
      try:
        other = type(self)(other)
      except Exception:
        return False
    return all(
        self[field.id] == other[field.id]
        for field in type(self).__id_fields__
        if self[field.id] or other[field.id])


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

    Only works for lists of Struct type. Usage: list.Get(field__subfield=3)
    """
    if not issubclass(self.sub_type, BaseStruct):
      raise TypeError('Cannot use Get on a List of non-Struct types.')

    def _CheckFunc(val):
      for attr, value in kwargs.items():
        if '__' not in attr:
          if val[attr] != value:
            return False
          continue
        # x.Get(a__b=5) -> Check .a.b == 5
        attrs = attr.split('__')
        # v = .a.b
        local_v = val
        for attr in attrs:
          local_v = local_v[attr]
        # Check v == 5
        if local_v != value:
          return False
      return True
    return next(val for val in self if _CheckFunc(val))

  @classmethod
  def ReplaceTypes(cls, template_map, memo=None):
    new_sub_type = generics.ReplaceType(cls.sub_type, template_map, memo=memo)
    if hasattr(new_sub_type, 'ReplaceTypes'):
      new_sub_type = new_sub_type.ReplaceTypes(template_map, memo=memo)
    if cls.sub_type == new_sub_type:
      return cls
    return List(new_sub_type)


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


def Interface(name, id):
  return InterfaceMeta(name, (BaseInterface,), {'id': id})


def _find_interface_base_class(cls, interface=None):
    if interface is not None:
        return interface
    interfaces = set(BaseInterface.__subclasses__())
    for base in cls.mro():
        if base in interfaces:
            return base
    raise TypeError('No interface inferable from %s', cls)


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

  def ApplyTemplatesToKwargs(cls, kwargs, template_map, memo=None):
    methods = list(kwargs['methods'])
    for i, method in enumerate(methods):
      params = generics.ReplaceMaybeList(method.params, template_map, memo=memo)
      results = generics.ReplaceMaybeList(
          method.results, template_map, memo=memo)
      # Only copy the method if it's going to change.
      if params is not method.params or results is not method.results:
        method = copy.copy(method)
        method.params = params
        method.results = results
        methods[i] = method
    kwargs['methods'] = methods
    kwargs['superclasses'] = [
        generics.ReplaceType(supercls, template_map, memo=memo)
        for supercls in kwargs['superclasses']]

  def ReplaceTypes(cls, template_map, memo=None):
    kwargs = {
        'methods': cls.__methods__.values(),
        'superclasses': cls.__superclasses__,
        'annotations': cls.__annotations__,
    }
    cls.ApplyTemplatesToKwargs(kwargs, template_map, memo=memo)
    new_decl = Interface(cls.__name__, cls.id)
    new_decl.ApplyTemplatesToNested(cls.__nested__, template_map, memo=memo)
    if (kwargs['methods'] != cls.__id_methods__
            or kwargs['superclasses'] != cls.__superclasses__
            or kwargs['annotations'] != cls.__annotations__
            or new_decl.__nested__ != cls.__nested__):
        # Something changed, so return a new interface declaration.
        new_decl.FinishDeclaration(**kwargs)
        return new_decl
    return cls

  def FinishDeclaration(cls, methods=None, superclasses=None, annotations=None):
    """Put all Method instances into __methods__."""
    cls.__superclasses__ = tuple(superclasses or ())
    cls.__annotations__ = annotations or []
    cls_methods = cls.__methods__ = {}
    id_methods = cls.__id_methods__ = {}
    for method in methods or []:
      cls_methods[method.name] = method
      id_methods[method.id] = method
    # Lastly, only allow __new__ to be overridden on the declaration class.
    cls.__new__ = cls.NewWrapper

  def __eq__(cls, other):
    return cls is other or (
        type(cls) is type(other)
        and len(cls.mro()) == len(other.mro())  # Subclasses
        and hasattr(cls, '__methods__') and hasattr(other, '__methods__')
        and cls.__superclasses__ == other.__superclasses__
        and cls.__methods__ == other.__methods__
        and cls.__annotations__ == other.__annotations__)

  def __hash__(cls):
    return object.__hash__(cls)

  def _get_method(cls, key):
    """Get method for the given key.

    Args:
      key: Method ID, method name or (interface ID, method ID). If just method
        ID or name, the interface ID is looked up. Otherwise, the interface ID
        is used to get the correct method.
    Returns: Interface ID, Method object.
    """
    if isinstance(key, tuple):
      # (interface id, method id), for when a particular method is called.
      id, method_id = key
      if cls.id == id:
        # For this class, so just let the rest of the method execute.
        key = method_id
      else:
        # For a superclass, so return that early.
        for supercls in cls.__superclasses__:
          if supercls.id == id:
            return supercls._get_method(method_id)

    id = cls.id
    if isinstance(key, int):
      method = cls.__id_methods__.get(key)
    else:
      method = cls.__methods__.get(key)
    if not method:
      # Check superclasses.
      for supercls in cls.__superclasses__:
        id, method = supercls._get_method(key)
        if method is not None:
          break
    return id, method


class BaseInterface(metaclass=InterfaceMeta):
  __slots__ = ()
  remote_type_registry = type_registry.TypeRegistry()

  def NewWrapper(cls, value):
    """Potentially creates an instance of cls.

    Here are the situations __new__ would be called:
        * By the framework when converting arguments to a method or elements of
            a struct.
            * With a BaseInterface subclass instance:  (Case 1)
                This can't just return the pased in Foo() because Python will
                call __init__ on the already-initialized Foo instance. Instead,
                we still have to wrap it.
                struct.attr = Foo()  # FooInterface(Foo()) -> wrapped
                Foo().method(Foo())  # FooInterface(Foo()) -> wrapped
            * With a class or function to be converted/wrapped:  (Case 2)
                struct.attr = OtherFoo()  # FooInterface(OtherFoo()) -> wrapped
                struct.attr = lambda: ... # FooInterface(function) -> wrapped
            * With an instance of this Interface: (Case 3)
                Since we have no __init__, it's safe to call it multiple times,
                so we can just return an already-initialized version of
                this class.
                _ConvertToType(FooInterface, FooInterface())
                # FooInterface(FooInterface()) -> original instance
            We're __new__ in both cases.
        * By the user on a subclass, which we should ignore. So we're not
            __new__ here.
    """
    # NOTE: Cannot use singledispatch here since value can be all sorts of
    # incompatible types (like dict, since singledispatch makes weakrefs and you
    # can't get a weakref to a dict).
    if cls.remote_type_registry.IsInstanceOfAny(value):
      # value came over the wire, so allow backends to send method calls back.
      return cls.remote_type_registry.LookUp(value)(cls, value)
    # Case 3
    if isinstance(value, cls):
        base_interface = _find_interface_base_class(type(value))
        if base_interface is type(value):
            return value
    # Case 1 & 2
    result = super().__new__(cls)
    result.__wrapped__ = value
    if len(cls.__methods__) > 1 and inspect.isfunction(value):
      raise TypeError('Interface %s has too many methods to be registered '
                      'with only a function.' % cls)
    return result

  def __getitem__(self, key):
    _, method = type(self)._get_method(key)
    if method is None:
      raise KeyError(key)
    return self._WrapMethod(method)

  def __getattribute__(self, attr):
    """Must be getattribute to catch attributes on subclasses."""
    _, method = type(self)._get_method(attr)
    if method is not None:
      return self._WrapMethod(method)
    return super().__getattribute__(attr)

  def _WrapMethod(self, method):
    if isinstance(method, TemplatedMethod):
      # Wrap TemplatedMethods after the templates are available.
      def _Wrapper(*templates):
        return self._WrapMethod(method[templates])
      return generics.GetItemWrapper(_Wrapper)

    # Allow wrapping an object.
    if hasattr(self, '__wrapped__'):
      obj = self.__wrapped__
    else:
      obj = self
    if inspect.isfunction(obj):
      # Allow wrapping a function.
      return self._MethodWrapper(obj, method)
    if obj is self:
        # skip our getattribute when we're a direct subclass.
        func = super().__getattribute__(method.name)
    elif isinstance(obj, dict):
        # Allow wrapping a dict with functions instead of a class instance.
        func = obj[method.name]
    else:
        func = getattr(obj, method.name)
    return self._MethodWrapper(func, method)

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
      if isinstance(method.params, list):
        args = [_ConvertToType(param.type, arg)
                for param, arg in zip(method.params, args)]
        kwargs = {
            name: _ConvertToType(_GetParam(name, method.params).type, arg)
            for name, arg in kwargs.items()}
      else:
        # Only one input param, so force it to be
        if args:
          args = (_ConvertToType(method.params, args[0]),)
        elif kwargs:
          # kwargs doesn't make sense since the parameter doesn't have a name,
          # unless the kwargs are actually for the input parameter.
          args = (_ConvertToType(method.params, kwargs),)
          kwargs = {}
      result = func(*args, **kwargs)

      # Convert result to proper types now.
      if not isinstance(method.results, list):
        return _ConvertToType(method.results, result)
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
        return '%s(%s)' % (type(self).__qualname__, self.__wrapped__)
    return '%s()' % (type(self).__qualname__)
  __repr__ = __str__


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
    return self.ReplaceTypes(template_map, memo={})

  def FinishDeclaration(self, **kwargs):
    if self._finished:
      return
    # Mark as finished, then finish all things waiting on this to be finished.
    self._finished = True
    super().FinishDeclaration(**kwargs)
    for decl in self.__dependent_decls__:
      decl(kwargs)

  def ReplaceTypes(self, template_map, memo=None):
    # Filter the template_map to what's relevant to us.
    local_tpl_map = [
        (original, final)
        for original, final in template_map
        if isinstance(original, generics.Template) and original.cls == self
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
      new_decl.ApplyTemplatesToKwargs(kwargs, template_map, memo=memo)
      new_decl.FinishDeclaration(**kwargs)
      new_decl.ApplyTemplatesToNested(self.__nested__, template_map, memo=memo)

    # If not finished, return self.base_type(name) and mark it as needing to be
    # finished when self is finished.
    # new_decl = type(self).base_type(self.name)
    def get_name(type):
        if isinstance(type, generics.Template):
            return str(type.cls)
        return type.name if hasattr(type, 'name') else str(type)
    new_decl = type(self).base_type(name='%s[%s]' % (
        self.name, ', '.join(get_name(type) for _, type in local_tpl_map)),
        id=self.id)
    new_decl.__nested__ = generics.MARKER(
        'Nested classes are not available yet.')
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
  required_attributes = tuple(set(Method.required_attributes)
                              - set(BaseDeclaration.required_attributes))
  _finished = True

  def __getitem__(self, template_values):
    template_map = [
        (generics.MethodTemplate(i), value)
        for i, value in enumerate(generics.EnsureTuple(template_values))]
    return self.ReplaceTypes(template_map, memo={})

  def ReplaceTypes(self, template_map, memo=None):
    annotations = generics.ReplaceMaybeList(
        self.annotations, template_map, memo=memo)
    params = generics.ReplaceMaybeList(self.params, template_map, memo=memo)
    results = generics.ReplaceMaybeList(self.results, template_map, memo=memo)
    return Method(
        self.id, self.name, annotations=annotations,
        params=params, results=results)
