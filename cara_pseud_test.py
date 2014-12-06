import cara
import cara_pseud
import tornado
import tornado.testing
import pseud
from pseud._tornado import async_sleep

# from gen import readme_pep8
# TODO: Put this into an actual capnp file
FooIface = cara.Interface('FooIface')
FooIface.FinishDeclaration(methods=[
    cara.Method(id=0, name='callback',
                input_params=[cara.Param(id=0, name='foo', type=FooIface)],
                output_params=[])])
BarIface = cara.Interface('BarIface')
BazIface = cara.Interface('BazIface')
BarIface.FinishDeclaration(methods=[
    cara.Method(id=0, name='return_cb',
                input_params=[],
                output_params=[cara.Param(id=0, name='cb', type=BazIface)])])
BazIface.FinishDeclaration(methods=[
    cara.Method(id=0, name='call',
                input_params=[cara.Param(id=0, name='is_called', type=cara.Bool)],
                output_params=[])])


class PseudTest(tornado.testing.AsyncTestCase):

    @tornado.gen.coroutine
    def create_client_server(self):
        self.endpoint = b'ipc://hi'
        self.server = self.create_server()
        yield self.server.start()
        yield async_sleep(self.io_loop, 0.2)
        self.client = self.create_client()
        yield self.client.start()

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
        result = False

        @self.server.register_rpc
        def test():
            nonlocal result
            result = True

        yield self.client.test()
        assert result

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
        def return_cb():
            def cb(is_called):
                nonlocal called
                called = is_called
            return cb
        cb = yield BarIface(self.client).return_cb()
        yield cb.call(True)
        assert called
