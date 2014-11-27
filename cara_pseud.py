import cara
import msgpack


def setup_server(server):
    # Register Interface with the server
    handler = cara.RemoteInterfaceServer()

    def iface_to_mp(val):
        handler.register(id(val), val)
        return msgpack.packb(id(val))

    def mp_to_remote_iface(val):
        # hack to deal with the fact that this is for both Interface and
        # RemoteInterface going through this same function, and logging doing
        # weird stuff. Won't be in the final code.
        if isinstance(msgpack.unpackb(val), int):
            remote_id = msgpack.unpackb(val)
            return cara.RemoteInterfaceDescriptor(remote_id, None)
        remote_id, user_id = msgpack.unpackb(val)
        return cara.RemoteInterfaceDescriptor(
            remote_id, server.send_to(user_id))
    # TODO: fix this, it should be 4 functions, I think
    server_table = {
        100: (cara.Interface, iface_to_mp, mp_to_remote_iface),
        101: (cara.RemoteInterface, iface_to_mp, mp_to_remote_iface)}

    server.packer.translation_table = server_table
    server.register_rpc(handler.registered, 'registered')
    return server


def setup_client(client):
    handler = cara.RemoteInterfaceServer()

    def iface_to_mp(val):
        handler.register(id(val), val)
        return msgpack.packb((id(val), client.user_id))

    def mp_to_remote_iface(val):
        remote_id = msgpack.unpackb(val)
        return cara.RemoteInterfaceDescriptor(remote_id, client)
    client_table = {
        100: (cara.Interface, iface_to_mp, mp_to_remote_iface),
        101: (cara.RemoteInterface, iface_to_mp, mp_to_remote_iface)
    }
    client.packer.translation_table = client_table
    client.register_rpc(handler.registered, 'registered')
