# Using Interfaces over the Wire

Next up, we're going to show how to use cara on top of pseud with tornado, but
there's no reason you have to do that, other than some of the work has been
done for you.

To use cara with the server, we create and setup the server, then register an
interface with that server. A single server can export multiple interfaces as
long as their method names don't collide, so we don't recommend that. Instead,
use separate servers if possible.

## Server

```python
@tornado.gen.coroutine
def create_server(endpoint, io_loop):
  server = pseud.Server(
      b'server', io_loop=io_loop, security_plugin='trusted_peer')
  server.bind(endpoint)
  # The only important line!
  server = cara_pseud.setup_server(server)
  yield server.start()

  @cara_pseud.register_interface(server)
  class MyCalculator(Calculator):
    def add(self, first, second):
      return first + second
```

1. The `security_plugin` used must be one that allows the client to be
   registered with the server. If the client never sends an interface to the
   server, then `security_plugin` doesn't matter.
2. Calling `cara_pseud.setup_server` before the server is started is necessary
   to setup all the cara machinery before any requests actually come in.
3. `cara_pseud.register_interface` can be called in a multitude of ways. Just
   like interface instantiation, we recommend choosing one and sticking with
   it. The method shown is the least convenient as it creates an instance of
   `MyCalculator` with no arguments. If that's unacceptable, but you want to
   use a class, use the following:

```python
cara_pseud.register_interface(server, MyCalculator(*args))
```

## Client

```python
@tornado.gen.coroutine
def create_client(endpoint, io_loop):
  client = pseud.Client(
      b'server', io_loop=io_loop,
      security_plugin='plain', user_id=b'test', password=b'_')
  client.connect(endpoint)
  client = cara_pseud.setup_client(client)
  yield client.start()
  result = yield Calculator(client).add(2, 5)
  # result == 7
```

1. Again, `security_plugin` must send a `user_id`, and here `plain` is the
   simplest one. Since the server uses `trusted_peer`, the password is just
   ignored. This isn't recommended for production use at all, but
   [pseud authentication backends](http://pseud.readthedocs.org/en/latest/authentication.html)
   are outside the scope of this document.
2. Calling `cara_pseud.setup_client` before the client is used is necessary to
   have the cara machinery setup.
3. Wrapping the client with the interface to be used is how you get cara to use
   all the information in the schemas. It will check that the method exists,
   convert the arguments if necessary (eg, if you sent a dict with field names as
   keys, it will convert the keys to the field ids), as well as convert the
   return type(s). If the method called returns an interface, it can now be
   used as if it were a local interface.
