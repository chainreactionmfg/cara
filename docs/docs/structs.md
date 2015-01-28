# Using Structs

Define a schema with a struct. Refer to
[capnproto's language reference](http://capnproto.org/language.html) for more
than what's used here.

```capnp
# person.capnp
@`capnp id`;  # Not included to reduce errors caused by copy-pasting.

struct Person {
  name @0 :Text;
  phoneNumber @1 :Text;
}
```

Then compile it into a python file and you can use it almost exactly like a dict:

```python
from person_capnp import Person
```

There are two ways to create a struct for convenience.

```python
Person.Create(name='First Last') == Person({'name': 'First Last'})
```

The created Person class is a subclass of dict, so you can convert it to json:

```python
json.dumps(Person.Create(phoneNumber='1-800-555-CARA'))
```

The above outputs: ``{"1": "1-800-555-CARA"}``

"Wait!", you say, "`phoneNumber` isn't is the JSON result, it's now `1`". Well,
that's part of the benefit of cara. The underlying dict only stores the field
IDs instead of the names, which makes the serialization smaller, but everything
can be referenced by ID or name. The `1` is a string because JSON only allows
keys to be strings.


