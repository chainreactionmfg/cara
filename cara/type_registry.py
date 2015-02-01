class TypeRegistry(object):
  def __init__(self):
    self._registry = {}
    self._registry_types = ()

  def Register(self, base_type, registered):
    if base_type in self._registry:
      return
    self._registry[base_type] = registered
    self._registry_types += (base_type,)

  def LookUp(self, instance):
    for base_type, registered in self._registry.items():
      if isinstance(instance, base_type):
        return registered

  def IsInstanceOfAny(self, instance):
    return isinstance(instance, self._registry_types)
