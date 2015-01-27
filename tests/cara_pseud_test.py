import tornado
import tornado.testing
import pseud

import cara
from cara import cara_pseud
from tests.cara_pseud_test_capnp import FooIface, BarIface, BazIface


class PseudTest(tornado.testing.AsyncTestCase):

    def create_client_server(self):
        self.endpoint = b'ipc://pseud-test-ipc'
        self.server = self.create_server()
        self.client = self.create_client()
        return [self.server.start(), self.client.start()]

    def create_server(self):
        server = pseud.Server(
            b'server', io_loop=self.io_loop, security_plugin='trusted_peer')
        server.bind(self.endpoint)
        return cara_pseud.setup_server(server)

    def create_client(self):
        client = pseud.Client(
            b'server', io_loop=self.io_loop,
            security_plugin='plain', user_id=b'test', password=b'_')
        client.connect(self.endpoint)
        return cara_pseud.setup_client(client)

    @tornado.testing.gen_test
    def test_simple(self):
        yield self.create_client_server()

        @self.server.register_rpc
        def test():
            self.stop(True)

        yield self.client.test()
        self.assertTrue(self.wait())

    @tornado.testing.gen_test
    def test_call_client_cb(self):
        yield self.create_client_server()
        called = False

        class Foo(FooIface):
            def callback(self):
                nonlocal called
                called = True

        @cara_pseud.register_interface(self.server, FooIface)
        def calls_cb(foo):
            foo.callback()

        yield self.client.callback(Foo())
        assert called

    @tornado.testing.gen_test
    def test_call_server_cb(self):
        yield self.create_client_server()
        called = False

        @cara_pseud.register_interface(self.server, BarIface)
        def returnCb():
            def cb(is_called):
                nonlocal called
                called = is_called
            return cb
        cb = yield BarIface(self.client).returnCb()
        yield cb.call(True)
        assert called
