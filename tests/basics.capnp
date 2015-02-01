@0xdeadbeef00110000;

# Ensure these exist and can be used.
using Schema = import "/capnp/schema.capnp";
using Persistent = import "/capnp/persistent.capnp";
using Rpc = import "/capnp/rpc.capnp";
using TwoParty = import "/capnp/rpc-twoparty.capnp";

struct Basic {
  field @0 :Int32;
  type @1 :Schema.Type;
  list @2 :List(Basic);
  ints @3 :List(Int32);
}

interface SimpleInterface {
  structOut @0 (input :Int32) -> Basic;
  structIn @1 Basic -> (output :Int32);
}
