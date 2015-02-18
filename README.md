# CARA
[![Build Status](https://img.shields.io/travis/chainreactionmfg/cara/master.svg)](https://travis-ci.org/chainreactionmfg/cara)
[![Coverage Status](https://img.shields.io/coveralls/chainreactionmfg/cara/master.svg)](https://coveralls.io/r/chainreactionmfg/cara)
[![Codacy Badge](https://img.shields.io/codacy/3cc5a370c923435e92b9ce1a7dbbbafe.svg)](https://www.codacy.com/public/fahhem/cara)
[![Documentation Status](https://readthedocs.org/projects/cara/badge/?version=latest&style=flat)](https://readthedocs.org/projects/cara/?badge=latest)
[![PyPI Version](https://img.shields.io/pypi/v/cara.svg)](https://pypi.python.org/pypi/cara)
[![PyPI License](https://img.shields.io/pypi/l/cara.svg)](https://pypi.python.org/pypi/cara)

<!--- Short Description --->
cara is a Cap'n proto Alternative RPC API.
[Read the docs!](http://cara.readthedocs.org/en/latest/)

## Reason for creation

pycapnp is a straight C++ conversion and, while that's great and all, it's not
pythonic. It also uses capnp's RPC layer and friends, which is from scratch and
isn't very mature, while there are plenty of RPC layers, event loops, etc
already in python and well-maintained.

## Requirements

To install via setup.py (or pip), a capnproto installation must be locatable by
pkg-config. Installed via a normal 'sudo make install' should work, other
situations have not been tested.

## Usage

First, generate the code from your .capnp files:

    capnp compile -ocara my_structs.capnp

Then import them:

    import my_structs

### Example

my_structs.capnp

    struct MyStruct {
        field @0 :Text;
        nested @1 :NestedStruct;
        struct NestedStruct {
            integer @0 :Int32;
        }
    }

Python usage

    import my_structs

    my_structs.MyStruct({'field': 'some text for here'})
    # -- or --
    m = my_struct.MyStruct.Create(field='some different text')

    # All the classes masquerade as python builtins, like dict:
    msgpack.packb(m) == b'\x81\x00\xb3some different text'
    # But it's slightly different... Look at Field Shrinking below to
    # understand

## Pseud Integration

There's also [pseud](https://github.com/ezeep/pseud) integration. Pseud
supports tornado and gevent, but only tornado on Python 3, so these examples
used tornado. If you use Python 2, you're welcome to use gevent.

The first requirement imposed is that you call cara_pseud.setup_server on your
server and cara_pseud.setup_client on your client. Once both are called, you
can start the server and client. For the server, register an interface with the
class or function you want to export. For the client, wrap the client object
with the interface you want to use it as. This API allows a server to export
multiple interfaces and a client to use any number of them.

### Example

my_ifaces.capnp

    interface SimpleEcho {
        echo (text :Text) -> (text :Text);
    }

    interface BackAndForth {
        interface Callback {
            callback (callback :Callback) -> (result :Text);
        }
        callMeMaybe (callback :Callback) -> ();
        otherFunc () -> ();
    }

Python usage:

    from cara import cara_pseud
    from my_ifaces import SimpleEcho, BackAndForth

    @tornado.gen.coroutine
    def create_server():
      server = pseud.Server(...)
      server.bind(...)
      cara_pseud.setup_server(server)
      yield server.start()

      # A function can be used to implement an interface with a single
      # method. The name doesn't have to match either.
      @cara_pseud.register_interface(server, SimpleEcho)
      def func(text):
        return text

      # If an interface has multiple methods, a class is necessary. It also has
      # to implement all the methods, but its name can be anything, too.
      # It can subclass the interface or object, but if you choose the
      # interface, the register_interface call can infer it from the class
      # definition.
      @cara_pseud.register_interface(server)
      class Server(BackAndForth):
        def callMeMaybe(self, callback):
          # You can even use a lambda as an interface.
          callback(lambda: 'internal callback')

        def otherFunc(self):
          pass

    @tornado.gen.coroutine
    def create_client():
      server = pseud.Client(...)
      server.connect(...)
      cara_pseud.setup_client(server)
      yield client.start()

      echo_iface = SimpleEcho(client)
      result = yield echo_iface.echo('test')
      assert result == 'test'

      # Now let's mess with this exported interface.
      back_and_forth = BackAndForth(client)
      # This is a special combination of fortunate accidents. A method with one
      # argument that is an interface with one method can be called like a
      # decorator. Though, you need to yield it still.
      @back_and_forth.callMeMaybe
      def callback(callback=None):
        result = yield callback()
        assert result == 'internal callback'
      yield callback

    io_loop.add_callback(create_server)
    io_loop.add_callback(create_client)
    io_loop.start()

## Field Shrinking

    # Notice there's no mention of 'field' in the result:
    m = {'field': 'some different text'}
    msgpack.packb(m) == b'\x81\xa5field\xb3some different text'
    # Yet there it is!

The difference is because a cara Struct uses the ordinals of the fields instead
of their names. This will only be an issue when sending the packed bytes over
to another system that isn't using cara. If you send it back into cara, it'll
unpack the fields correctly and you can use it like the original pieces.

    original = my_structs.MyStruct.Create(nested={'integer': 2})
    packed = msgpack.packb(original)
    unpacked = msgpack.unpackb(packed)
    # --> {1: {0: 2}}
    result = my_structs.MyStruct(unpacked)
    # --> MyStruct({nested: NestedStruct({integer: 2})})

This allows us to serialize a struct into a much smaller bytestring, especially
since 0-127 becomes a single byte in msgpack. As long as your capnp schema
changes are sufficiently backwards-compatible, you can deserialize and lookup
the field numbers to get the appropriate type.

