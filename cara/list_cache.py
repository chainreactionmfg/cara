from crmfg_utils import records


class ListCache(records.Record('ListCache', [],
                               {'keys': list, 'values': list})):
  def __setitem__(self, key, value, key_idx=None):
    self.keys.append(key)
    self.values.append(value)

  def __contains__(self, key):
    return key in self.keys

  def __getitem__(self, key):
    return self.values[self.keys.index(key)]

  def get(self, key, default=None):
    try:
      idx = self.keys.index(key)
    except ValueError:
      return default
    else:
      return self.values[idx]
