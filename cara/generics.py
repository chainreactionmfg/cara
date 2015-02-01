import copy

from crmfg_utils import records


def ReplaceObject(obj, template_map):
  type_replacement = ReplaceType(obj.type, template_map)
  if type_replacement is obj.type:
    return obj
  # Create a copy with the modified type.
  obj = copy.copy(obj)
  obj.type = type_replacement
  return obj


def ReplaceType(type, template_map):
  if type.__class__.__name__ == 'BaseTemplated':
    return type.ReplaceTypes(template_map)
  elif isinstance(type, Template):
    for template, replacement in template_map:
      # Avoid == recursion issues.
      if (isinstance(template, Template) and
          type.cls is template.cls and type.id == template.id):
        return replacement
  elif isinstance(type, MethodTemplate):
    for template, replacement in template_map:
      if (isinstance(template, MethodTemplate) and
          type.id == template.id):
        return replacement
  elif isinstance(type, Templated):
    return type.ReplaceTypes(template_map)
  else:
    for template, replacement in template_map:
      if template == type:
        return replacement
  return type


def ReplaceMaybeList(lst, template_map):
  if isinstance(lst, list):
    replacement = [ReplaceObject(obj, template_map) for obj in lst]
    if any(rep is not obj for rep, obj in zip(replacement, lst)):
        return replacement
    # Nothing changed, so don't modify the list either.
    return lst
  return ReplaceType(lst, template_map)


Template = records.ImmutableRecord('Template', ['cls', 'id'])
MethodTemplate = records.ImmutableRecord('MethodTemplate', ['id'])


class Templated(records.ImmutableRecord(
    'Templated', ['cls', 'template_map'])):
  # self.template_map is a map from original to intermediary (or to final).
  def ReplaceTypes(self, template_map):
    # the template_map argument is a map from intermediary to final.
    resulting_map = []
    full = True
    for original, intermediary in self.template_map:
      if not isinstance(intermediary, Template):
        # intermediary is actually a final value.
        resulting_map.append((original, intermediary))
        continue
      for mapped, value in template_map:
        if intermediary == mapped:
          resulting_map.append((original, value))
          break
      else:
        # Replacement not found.
        resulting_map.append((original, intermediary))
        full = False

    if full:
      # Replacing all templates, so return the actual class properly templated.
      return self.cls.ReplaceTypes(resulting_map)
    if resulting_map != self.template_map:
      # Partially replaced, return a new version of ourselves.
      return type(self)(self.cls, resulting_map)
    # Nothing changed.
    return self

  def __getattr__(self, attr):
    # Nested classes only.
    return type(self)(getattr(self.cls, attr), self.template_map)

  def __getitem__(self, template_values):
    template_map = [(self.cls.Template(i), value)
                    for i, value in enumerate(EnsureTuple(template_values))]
    return self.ReplaceTypes(template_map)


def EnsureTuple(obj):
  if isinstance(obj, tuple):
    return obj
  return (obj,)


class GetItemWrapper(records.ImmutableRecord('GetItemWrapper', ['func'])):

  def __getitem__(self, item):
    return self.func(item)
