# Using Interfaces

Add an interface to the schema and you can use it locally with ease:

```capnp
interface Calculator {
  add @0 (first :Int32, second :Int32) -> (result :Int32);
}
```

The resulting filename gets `_capnp.py` suffixed:

```python
from calculator_capnp import Calculator
```

## Instantiation

The easiest way is to wrap a dict with functions.

```python
calc = Calculator({
  'add': lambda first, second: first + second,
})
calc.add(1, second=2) == 3
```

Or wrap an object with methods. In the following case, it's an interface
instance, but it can be any object with the necessary methods.

```python
calc = Calculator(calc)
```

Or subclass the interface and any instance of that new class will work.

```python
class MyCalculator(Calculator):
  def add(self, first, second):
    return first + second

MyCalculator().add(10, 20) == 30
```

Interfaces can be created in many ways, as seen above. We recommend choosing
one and sticking to it, though the dict-with-lambdas approach is just too
convenient to pass up sometimes.

