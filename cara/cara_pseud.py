import concurrent.futures
import inspect

from cara import cara
from crmfg_utils import records

import msgpack
import tornado.concurrent

RemoteInterfaceDescriptor = records.ImmutableRecord(
    'RemoteInterfaceDescriptor', ['remote_id', 'client'])


class RemoteInterfaceServer(records.Record('Wrapper', [], {'objs': dict})):

  def registered(self, local_id, method_id, args, kwargs):
    return self.objs[local_id][method_id](*args, **kwargs)

  def register(self, local_id, obj):
    self.objs[local_id] = obj


class RemoteInterfaceClient(records.ImmutableRecord(
        'RemoteInterface', ['remote_id', 'client', 'methods', 'id_methods'])):

  @classmethod
  def FromDescriptor(cls, interface, descriptor):
    return cls(
        descriptor.remote_id, descriptor.client,
        interface.__methods__, interface.__id_methods__)

  def __getattr__(self, attr):
      if isinstance(attr, int):
          attr = self.id_methods[attr]
      method = self.methods.get(attr)
      if method is None:
          raise AttributeError('%s has no attribute %s' % (self, attr))
          super().__getattr__(attr)

      def ProxyMethod(*args, **kwargs):
          return self.client.registered(self.remote_id, method.id, args, kwargs)
      return cara.BaseInterface._MethodWrapper(ProxyMethod, method)
  __getitem__ = __getattr__


def setup_server(server):
    _RegisterPseudBackend()
    # Register Interface with the server
    handler = RemoteInterfaceServer()

    def iface_to_mp(val):
        handler.register(id(val), val)
        return msgpack.packb(id(val))

    def mp_to_remote_iface(val):
        # hack to deal with the fact that this is for both Interface and
        # RemoteInterface going through this same function, and logging doing
        # weird stuff. Won't be in the final code.
        if isinstance(msgpack.unpackb(val), int):
            remote_id = msgpack.unpackb(val)
            return RemoteInterfaceDescriptor(remote_id, None)
        remote_id, user_id = msgpack.unpackb(val)
        return RemoteInterfaceDescriptor(remote_id, server.send_to(user_id))
    # TODO: fix this, it should be 4 functions, I think
    server_table = {
        100: (cara.BaseInterface, iface_to_mp, mp_to_remote_iface),
        101: (RemoteInterfaceClient, iface_to_mp, mp_to_remote_iface)}

    server.packer.translation_table = server_table
    server.register_rpc(handler.registered, 'registered')
    return server


def setup_client(client):
    _RegisterPseudBackend()
    handler = RemoteInterfaceServer()

    def iface_to_mp(val):
        handler.register(id(val), val)
        return msgpack.packb((id(val), client.user_id))

    def mp_to_remote_iface(val):
        remote_id = msgpack.unpackb(val)
        return RemoteInterfaceDescriptor(remote_id, client)
    client_table = {
        100: (cara.BaseInterface, iface_to_mp, mp_to_remote_iface),
        101: (RemoteInterfaceClient, iface_to_mp, mp_to_remote_iface)
    }
    client.packer.translation_table = client_table
    client.register_rpc(handler.registered, 'registered')
    return client


def _RegisterPseudBackend():
  def ConvertFutureCorrectly(type, future):
    """Converts a future's result into the given type.

    Instead of converting the future into the given type directly, we create a
    chained future that converts the type later.
    """
    new_future = tornado.concurrent.Future()

    def _Done(fut):
        new_future.set_result(cara._ConvertToType(type, fut.result()))

    future.add_done_callback(_Done)
    # For exceptions only:
    tornado.concurrent.chain_future(future, new_future)
    return new_future
  # First register the future conversions of method calls.
  registry = cara.__type_conversion_registry__
  registry[tornado.concurrent.Future] = ConvertFutureCorrectly
  registry[concurrent.futures.Future] = ConvertFutureCorrectly
  # Next register the remote descriptor handler for when those method calls
  # return a remote interface.
  cara.BaseInterface.register_remote_type(
      RemoteInterfaceDescriptor, RemoteInterfaceClient.FromDescriptor)


def _find_interface(cls, interface):
    if interface is not None:
        return interface
    for base in cls.mro():
        if issubclass(base, cara.BaseInterface):
            return base
    raise TypeError('No interface inferable from %s', cls)


def register_interface(server, interface=None, obj_or_cls=None):
    """Registers an object with the given server (or client).

    Call this with a server and an object, and optionally an interface.

    If called with only a server, it will become a decorator and must be called
    on a class that can be constructed with no arguments. If the interface has a
    single method, then it may also decorate a function.

    If the interface is not specified, then the object must be a subclass of an
    interface.

    interface FooInterface {
        bar @0 () -> ();
    }

    @register_interface(server)
    class Foo(FooInterface):
        ...

    @register_interface(server, interface=FooInterface)
    class Foo:
        ...

    @register_interface(server, interface=FooInterface)
    def bar_func():
        ...

    register_interface(server, FooInterface, FooClass)
    register_interface(server, FooInterface, bar_func)
    """

    def decorator(obj_or_cls):
        nonlocal interface
        if inspect.isclass(obj_or_cls):
            obj = obj_or_cls()
            interface = _find_interface(obj_or_cls, interface)
        elif inspect.isfunction(obj_or_cls):
            if interface is None:
                raise TypeError('Interface must be specified for registering a '
                                'single function.')
            if len(interface.__methods__) != 1:
                raise TypeError(
                    'Interface %s has too many methods to be registered with '
                    'only a function.' % interface)
            obj = interface(obj_or_cls)
        else:
            # Should be an instance of a class.
            interface = _find_interface(obj_or_cls.__class__, interface)
            obj = interface(obj_or_cls)

        for name, method in interface.__methods__.items():
            func = getattr(obj, name)
            server.register_rpc(func, name=name)
    if obj_or_cls is None:
        return decorator
    return decorator(obj_or_cls)
