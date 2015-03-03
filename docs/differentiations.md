# Differentiations

## Schema definition layer

The first and biggest difference between this and all other (except for one)
RPC layers is the schema definition layer. Schema definitions are in
[Capnproto](http://capnproto.org/language.html "Capnproto schema language"),
which, among other things, has support for interfaces as first-class citizens.
This means interfaces can be passed around, sent over the wire, etc.

```capnp

interface AddressBook {
  find @0 (name :Text) -> Person;
}

struct Person {
  name @0 :Text;
  ...
  interface UpdatePerson {
    update @0 Person -> ();
    delete @1 () -> ();
  }
  updater @1 :UpdatePerson;
}
```

The great benefit of this ability in the schema means we can express more
clearly what we want to do. In the above schema, you can `find` a person by
name, and then update them or even delete them by calling
`person.updater.delete()`.

In an API that does not have this, you go through this circuitous route of
getting the ID of the person and then calling the appropriate method on the
`AddressBook` and pass in that ID. While that is possible, and essentially what
REST APIs have at their foundation, it can get convoluted as there are many
ways to get the ID of a `Person` and many uses of that ID.

With the interface passed with the struct, you get clear information about what
is even possible with the record you received. In fact, you could even return a
read-only version of a record that has no interfaces that allow writing, but
only reading, or limit what they can read by not providing interfaces to
retrieve the phone number, address, or any other sensitive data.

This works in this schema because by passing an interface to a client,
permission to use that interface is implicitly granted. No further
authentication is necessary and the client can use any interfaces received.

## From pycapnp

While the schema definition layer is exactly the same as with `pycapnp`, cara
is agnostic as to the serialization and networking layer. This allows you to
use whatever layers your project already uses, as well as experiment with
others. The driving force behind cara was to use the best of every layer and
not let any one layer dictate the others. With cara, you can do anything you
wish.

The one thing it doesn't support at the moment is zero-copy (de)serialization
that pycapnp does. However, if your application needs zero-copy for speed, then
you're not likely to be using Python anyway. However, zeromq and msgpack both
have zero-copy solutions it their C++ implementations, getting you pretty close
to capnp's claimed 0us times, without enforcing its ideas on how you allocate,
set, and get your data.
