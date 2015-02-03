import copy

from crmfg_utils import records

MARKER = records.ImmutableRecord('ObjectMarker', ['name'])
NID = MARKER('Not in dict')
InProgress = records.ImmutableRecord('InProgress', ['obj'])


def ReplaceObject(obj, template_map, memo=None):
  # Manage possible recursion caused by the ReplaceTypes call below.
  d = id(obj)
  memo = memo or {}
  cached = memo.get(d, NID)
  if cached is not NID:
    if isinstance(cached, InProgress):
      return cached.obj
    return cached
  memo[d] = InProgress(obj)

  type_replacement = ReplaceType(obj.type, template_map, memo=memo)
  if type_replacement is obj.type:
    if hasattr(type_replacement, 'ReplaceTypes'):
      type_replacement = type_replacement.ReplaceTypes(template_map, memo=memo)
    if type_replacement is obj.type:
      return obj
  # Create a copy with the modified type.
  obj = copy.copy(obj)
  obj.type = type_replacement
  memo[d] = obj
  return obj


def ReplaceType(type, template_map, memo=None):
  d = id(type)
  memo = memo or {}
  cached = memo.get(d, NID)
  if cached is not NID:
    return cached

  if type.__class__.__name__ == 'BaseTemplated':
    ret = memo[d] = type.ReplaceTypes(template_map, memo=memo)
    return ret
  elif isinstance(type, Template):
    for template, replacement in template_map:
      # Avoid == recursion issues.
      if (isinstance(template, Template) and
          type.cls is template.cls and type.id == template.id):
        ret = memo[d] = replacement
        return ret
  elif isinstance(type, MethodTemplate):
    for template, replacement in template_map:
      if (isinstance(template, MethodTemplate) and
          type.id == template.id):
        ret = memo[d] = replacement
        return ret
  elif isinstance(type, Templated):
    ret = memo[d] = type.ReplaceTypes(template_map, memo=memo)
    return ret
  else:
    for template, replacement in template_map:
      if template == type:
        ret = memo[d] = replacement
        return ret
  memo[d] = type
  return type


def ReplaceMaybeList(lst, template_map, memo=None):
  if isinstance(lst, list):
    replacement = [ReplaceObject(obj, template_map, memo=memo) for obj in lst]
    if any(rep is not obj for rep, obj in zip(replacement, lst)):
        return replacement
    # Nothing changed, so don't modify the list either.
    return lst
  return ReplaceType(lst, template_map, memo=memo)


Template = records.ImmutableRecord('Template', ['cls', 'id'])
MethodTemplate = records.ImmutableRecord('MethodTemplate', ['id'])


class Templated(records.ImmutableRecord(
        'Templated', ['cls', 'template_map'])):
  # self.template_map is a map from original to intermediary (or to final).
  def ReplaceTypes(self, template_map, memo=None):
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
      return self.cls.ReplaceTypes(resulting_map, memo=memo)
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
    return self.ReplaceTypes(template_map, memo={})


def EnsureTuple(obj):
  if isinstance(obj, tuple):
    return obj
  return (obj,)


class GetItemWrapper(records.ImmutableRecord('GetItemWrapper', ['func'])):

  def __getitem__(self, item):
    return self.func(item)
