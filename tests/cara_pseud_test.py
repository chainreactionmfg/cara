from unittest import mock

import tornado.testing
import pseud
import zmq

import cara
from cara import cara_pseud
from tests.cara_pseud_test_capnp import FooIface, BarIface, BazIface


class PseudTest(tornado.testing.AsyncTestCase):

    def setUp(self):
        super().setUp()
        self.endpoint = b'ipc://pseud-test-ipc'
        # Don't let pseud make any real contexts.
        patch = mock.patch.object(pseud.Server, '_make_context')
        mock_context = patch.start()
        self.addCleanup(patch.stop)
        mock_context.return_value.socket.return_value.mechanism = zmq.PLAIN

        # Return a stream mock that sends packets to the other stream.
        patch = mock.patch.object(
            zmq.eventloop.zmqstream, 'ZMQStream')
        self.stream_mock = patch.start()
        self.addCleanup(patch.stop)
        self.stream_mock.side_effect = self.create_stream

    def create_stream(self, socket, io_loop):
        new_stream = mock.MagicMock()
        new_stream.socket = socket
        def send_effect(data, callback):
            data = [zmq.Frame(frame) for frame in data]
            # Send data to the _other_ stream.
            other_stream = (
                self.server_stream
                if new_stream is self.client_stream
                else self.client_stream)
            call = other_stream.on_recv.mock_calls[0]
            name, args, kwargs = call
            with mock.patch.object(data[-1], 'get'):
                # Have to make the User-Id return our username.
                username = new_stream.socket.plain_username
                if isinstance(username, (bytes, str)):
                    data[-1].get.return_value = username.decode('utf-8')
                args[0](data)
            callback()
        new_stream.send_multipart.side_effect = send_effect
        return new_stream

    def create_client_server(self):
        self.server = self.create_server()
        self.client = self.create_client()
        starts = [self.server.start(), self.client.start()]
        self.server_stream = self.server.reader
        self.client_stream = self.client.reader
        return starts

    def create_server(self):
        server = pseud.Server(
            b'server', io_loop=self.io_loop, security_plugin='trusted_peer')
        server.bind(self.endpoint)
        return cara_pseud.setup_server(server)

    def create_client(self):
        client = pseud.Client(
            b'server', io_loop=self.io_loop,
            security_plugin='plain', user_id=b'client', password=b'_')
        client.connect(self.endpoint)
        return cara_pseud.setup_client(client)

    @tornado.testing.gen_test(timeout=0.5)
    def test_simple(self):
        yield self.create_client_server()

        @self.server.register_rpc
        def test():
            self.stop(True)

        yield self.client.test()
        assert self.wait()

    @tornado.testing.gen_test(timeout=0.5)
    def test_call_client_cb(self):
        yield self.create_client_server()

        class Foo(FooIface):
            def callback(foo_self):
                self.stop(True)

        @cara_pseud.register_interface(self.server, FooIface)
        def calls_cb(foo):
            foo.callback()

        yield self.client.callback(Foo())
        assert self.wait()

    @tornado.testing.gen_test(timeout=0.5)
    def test_call_server_cb(self):
        yield self.create_client_server()

        @cara_pseud.register_interface(self.server, BarIface)
        def returnCb():
            def cb(is_called):
                self.stop(is_called)
            return cb
        cb = yield BarIface(self.client).returnCb()
        yield cb.call(True)
        assert self.wait()
