import collections
from unittest import mock

import tornado.testing
import pseud
import pytest
import zmq

import cara
from cara import cara_pseud
from tests.cara_pseud_test_capnp import (
    FooIface, BarIface, BazIface, ThreeIface, Super, Inherit, InheritAcceptor)


@pytest.fixture
def stream_mock(request):
    # Don't let pseud make any real contexts.
    patch = mock.patch.object(zmq.Context, 'instance')
    mock_context = patch.start()
    request.addfinalizer(patch.stop)

    # Create a new mock socket so the binds and connects don't combine.
    def create_socket(sock_type):
        socket = mock.MagicMock()
        socket.mechanism = zmq.PLAIN
        return socket
    mock_context.return_value.socket.side_effect = create_socket

    # Return a stream mock that sends packets to the other stream.
    patch = mock.patch.object(
        zmq.eventloop.zmqstream, 'ZMQStream')
    stream_mock = patch.start()
    request.addfinalizer(patch.stop)

    # endpoint -> stream
    stream_mock.servers = servers = {}
    # endpoint -> routing_id -> stream
    stream_mock.clients = clients = collections.defaultdict(dict)
    stream_mock.packets = packets = []
    streams = {}

    def create_stream(socket, io_loop):
        stream = mock.MagicMock()
        stream.socket = socket
        is_server = False
        endpoint = None

        def send_effect(data):
            if not is_server:
                clients[endpoint][stream.socket.plain_username] = stream
            # Send data to the _other_ stream.
            if is_server:
                # Server uses the ROUTER's routing id (which we set).
                other_stream = clients[endpoint][data[0]]
            else:
                other_stream = servers[endpoint]

            if not is_server:
                # Act like a ROUTER socket and set our username as the
                # routing id.
                data[0] = stream.socket.plain_username
            packets.append((streams[stream], streams[other_stream], data))
            data = [zmq.Frame(frame) for frame in data]

            call = other_stream.on_recv.mock_calls[0]
            name, args, kwargs = call
            on_recv_cb = args[0]
            with mock.patch.object(data[-1], 'get'):
                # Have to make the User-Id return our username.
                if not is_server or True:
                  username = stream.socket.plain_username
                  if isinstance(username, (bytes, str)):
                    data[-1].get.return_value = username.decode('utf-8')
                on_recv_cb(data)

        # Get the last endpoint the socket was bound to.
        for (name, args, kwargs) in reversed(socket.mock_calls):
            if name == 'bind':
                endpoint = args[0]
                is_server = True
                break
            if name == 'connect':
                endpoint = args[0]
                break
        if is_server:
            servers[endpoint] = stream
            streams[stream] = socket.identity
            stream.send_multipart.side_effect = send_effect
        else:
            # routing id unknown until first send for clients.
            streams[stream] = stream.socket.plain_username
            stream.send_multipart.side_effect = send_effect
        return stream
    stream_mock.side_effect = create_stream
    # Make the stream mock available on the class.
    request.cls.stream_mock = stream_mock
    return stream_mock


class BasePseudTest(tornado.testing.AsyncTestCase):
    def create_server(self, endpoint):
        server = pseud.Server(
            b'server', io_loop=self.io_loop, security_plugin='trusted_peer')
        server.bind(endpoint)
        return cara_pseud.setup_server(server)

    def create_client(self, endpoint, user_id=b'client'):
        client = pseud.Client(
            b'server', io_loop=self.io_loop,
            security_plugin='plain', user_id=user_id, password=b'_')
        client.connect(endpoint)
        return cara_pseud.setup_client(client)


@pytest.mark.usefixtures('stream_mock')
class PseudTest(BasePseudTest):

    def create_client_server(self):
        endpoint = b'ipc://pseud-test-ipc'
        self.server = self.create_server(endpoint)
        self.client = self.create_client(endpoint)
        starts = [self.server.start(), self.client.start()]
        self.server_stream = self.server.reader
        self.client_stream = self.client.reader
        return starts

    @tornado.testing.gen_test(timeout=0.1)
    def test_simple(self):
        this = self
        yield self.create_client_server()

        @self.server.register_rpc
        def test():
            self.stop(True)

        @cara_pseud.register_interface(self.server)
        class BazIfaceImpl(BazIface):
            def call(self, is_called):
                this.stop(True)

        yield self.client.test()
        assert self.wait()
        yield BazIface(self.client).call(True)
        assert self.wait()

    @tornado.testing.gen_test(timeout=0.1)
    def test_call_client_cb(self):
        this = self
        yield self.create_client_server()

        class Foo(FooIface):
            def callback(self):
                this.stop(True)

        @cara_pseud.register_interface(self.server, FooIface)
        def calls_cb(foo):
            foo.callback()

        yield self.client.callback(Foo())
        assert self.wait()

    @tornado.testing.gen_test(timeout=0.1)
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

    @tornado.testing.gen_test(timeout=0.1)
    def test_inheritance(self):
        yield self.create_client_server()

        inherit_iface = {
            'superMethod': lambda: self.stop('super'),
            'inheritedMethod': lambda: self.stop('inherited'),
            'second': lambda: self.stop('second'),
            'third': lambda: self.stop('third'),
            'overlapped': lambda: self.stop('overlapped'),
        }

        cara_pseud.register_interface(self.server, Inherit, inherit_iface)
        yield Inherit(self.client).inheritedMethod()
        assert self.wait() == 'inherited'
        yield Inherit(self.client).superMethod()
        assert self.wait() == 'super'

        cara_pseud.register_interface(self.server, InheritAcceptor, {
            'accept': lambda iface: self.stop(iface)
        })
        yield InheritAcceptor(self.client).accept(inherit_iface)
        accepted = self.wait()
        assert isinstance(accepted, cara_pseud.RemoteInterfaceClient)
        yield accepted.superMethod()
        assert self.wait() == 'super'
        yield accepted.superMethod()
        assert self.wait() == 'super'
        yield accepted.inheritedMethod()
        assert self.wait() == 'inherited'


@pytest.mark.usefixtures('stream_mock')
class ProxyTest(BasePseudTest):

    class ThreeIfaceImpl(ThreeIface):
        def __init__(self):
            self._last = None

        def returnIface(self):
            return self._last

        def acceptIface(self, accept):
            self._last = accept

    @tornado.testing.gen_test(timeout=0.1)
    def test_three_parties(self):
        # Test three parties, A, B, and C. B sends an interface to A, then C
        # gets that interface from B. Calling a method on that interface on C
        # should proxy through A to B.
        # interface goes B -> A -> C
        server_a = self.create_server('ipc://party')
        client_b = self.create_client('ipc://party', user_id=b'client-b')
        client_c = self.create_client('ipc://party', user_id=b'client-c')

        cara_pseud.register_interface(
            server_a, ThreeIface, self.ThreeIfaceImpl())

        yield [server_a.start(), client_b.start(), client_c.start()]

        client_b = ThreeIface(client_b)
        client_c = ThreeIface(client_c)

        # B -> A
        yield client_b.acceptIface({'normalMethod': lambda input: 'output'})
        # C <- A
        iface_from_b = yield client_c.returnIface()

        # Call the interface from B through C.
        result = yield iface_from_b.normalMethod('input')
        assert result == 'output'

        expected = [
            # B -> A
            (b'client-b', b'server'),
            (b'server', b'client-b'),
            # C <- A
            (b'client-c', b'server'),
            (b'server', b'client-c'),
            # Call interface from B through C.
            (b'client-c', b'server'),  # C -> A
            (b'server', b'client-b'),  # A -> B
            (b'client-b', b'server'),  # A <- B
            (b'server', b'client-c'),  # C <- A
        ]
        for (expected_sender, expected_recv), (sender, recv, _) in zip(
                expected, self.stream_mock.packets):
            assert expected_sender == sender
            assert expected_recv == recv

    @tornado.testing.gen_test(timeout=0.1)
    def test_back_forth(self):
        server = self.create_server('ipc://date')
        client = self.create_client('ipc://date')

        cara_pseud.register_interface(server, ThreeIface, self.ThreeIfaceImpl)
        yield [server.start(), client.start()]

        client = ThreeIface(client)
        # Send interface.
        yield client.acceptIface({'normalMethod': lambda input: 'out'})
        # Get it back.
        mine = yield client.returnIface()
        # Should proxy through the server to ourselves.
        result = yield mine.normalMethod('in')
        assert result == 'out'

        expected = [
            # Send interface.
            (b'client', b'server'),
            (b'server', b'client'),
            # Get it back
            (b'client', b'server'),
            (b'server', b'client'),
            # Call the interface
            (b'client', b'server'),
            (b'server', b'client'),
            # Proxied through us.
            (b'client', b'server'),
            (b'server', b'client'),
        ]
        for (expected_sender, expected_recv), (sender, recv, _) in zip(
                expected, self.stream_mock.packets):
            assert expected_sender == sender
            assert expected_recv == recv
