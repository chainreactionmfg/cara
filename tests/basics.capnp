@0xdeadbeef00110000;

# Ensure these exist and can be used.
using Schema = import "/capnp/schema.capnp";
using Persistent = import "/capnp/persistent.capnp";
using Rpc = import "/capnp/rpc.capnp";
using TwoParty = import "/capnp/rpc-twoparty.capnp";

using Cara = import "/capnp/cara.capnp";

struct Basic @0xf950b63201d11192 $Cara.registerGlobally {
  field @0 :Int32;
  type @1 :Schema.Type;
  list @2 :List(Basic);
  ints @3 :List(Int32);
  nested @4 :Basic;
}

struct SemiAdvanced {
  namedGroup :group {
    first @0 :Text;
  }
  namedUnion :union {
    this @1 :Int32;
    that @2 :Int64;
  }
  union {
    unnamed @3 :Int8;
    unionField @4 :Data;
  }
}

interface SimpleInterface {
  structOut @0 (input :Int32) -> Basic;
  structIn @1 Basic -> (output :Int32);
  multipleOut @2 () -> (one :Int32, two :Int32);
}
