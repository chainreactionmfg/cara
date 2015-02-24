# Advanced Usage

## Global registry of structs and interfaces.

Adding an annotation to a struct or interface will add it to a registry in cara
with all their IDs. This allows the benefits of being able to lookup certain
types without registering all types.

```capnp
using Cara = import "/capnp/cara.capnp";
struct StructName @<capnp id> $Cara.registerGlobally {}
```

```python
import cara
cara.GlobalTypeRegistery[<capnp id>].__name__ == 'StructName'
```

## Replacing a struct or interface's implementation.

Sometimes you want to replace how a struct or interface is handled in your
application, but maybe only in your subset of the code. Calling `ReplaceTypes`
on a struct or interface with an item-map will replace any mention of the keyed
types with the values. To explain more simply, here's an example:

```capnp
# example.capnp
struct Root {
  field @0 :SubType1;
  struct SubType1 {
    subField @0 :Host;
  }
  struct Host {
    hostname @0 :Text;
    port @1 :Int16;
  }
}
```

First, import it as usual.

```python
from example_capnp import Root
```

Next, let's construct it with a dict, as normal.

```python
foo = Root({'field': {'subField': {'hostname': 'cara.readthedocs.org'}}})
assert foo.field.subField.hostname == 'cara.readthedocs.org'
```

Now, let's create a new class that takes a dict matching the `Host` struct.

```python
class HostReplacement(object):
  def __init__(self, dct):
    self._hostname = dct.get('hostname', 'www.google.com')
    self._port = dct.get('port', 80)
    self.socket = socket.create_connection((self._hostname, self._port))
```

Next, we create a new struct that is just like `Root`, except with our new
class in the right place. Note that we have to use a list of tuples, similar to
what a python dict's `items()` method returns, because many types aren't
hashable.

```python
NewRoot = Root.ReplaceTypes([(Root.Host, HostReplacement)])
new_foo = NewRoot(foo)
assert isinstance(new_foo.field.subField, HostReplacement)
```

Now the `NewRoot` struct is exactly the same as `Root`, except anywhere that
the `Host` struct was is now `HostReplacement`, even in its nested structs.
Note the names aren't changed, only the underlying type.

```python
assert NewRoot.Host is not Root.Host
assert NewRoot.Host is HostReplacement
```
