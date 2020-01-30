def flat_list(list2d):
    """flatten nested list"""
    return [x for sublist in list2d for x in sublist]


def return_other(_list, item):
    """from a list with 2 items, given one return the other"""
    if item == _list[0]:
        return _list[1]
    else:
        return _list[0]


def int_to_list(sv_id):
    """helper function to turn int input to list for request body creation
    in many BrainMapsAPI calls"""
    if type(sv_id) == int:
        return [sv_id]
    else:
        return sv_id


def keys_to_int(dct):
    return {int(k): v for k, v in dct.items()}


def convert_coord(coord, orig, targ=[9, 9, 25]):
    """convert coordinates from one resolution to the other"""
    newx = coord[0] * orig[0] / targ[0]
    newy = coord[1] * orig[1] / targ[1]
    newz = coord[2] * orig[2] / targ[2]
    return [newx, newy, newz]


class CustomList:
    """List object with a flag that indicates unsaved changes

    mimics list functions: remove, pop, add, append, __iadd__, __len__

    Additional functions:
    - isub: in-place subtraction of list items and
    - update: replace _data entries

    Attributes:
        _data (list)
        unsaved_changes (Boolean) : flag that indicates changes to the list that
                                    were not saved
        self.max_length (int) : variable that restricts list to a certain length
                                earlier entries are discarded if max_length is
                                exceeded
    """
    def __init__(self, data=None, max_length=None):
        if data is None:
            self._data = []
        else:
            self._data = data
        self.unsaved_changes = False
        self.max_length = max_length

    def __add__(self, other):
        self.__iadd__(other)

    def __delitem__(self, key):
        self.unsaved_changes = True
        self._data.pop(key)

    def __getitem__(self, key):
        return self._data[key]

    def __iadd__(self, other):
        self._data += other
        self.unsaved_changes = True
        self.check_length()
        return CustomList(self._data)

    def __isub__(self, other):
        self._data = [item for item in self if item not in other]
        return CustomList(self._data)

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return '{} {}'.format(self._data, self.__class__)

    def __reversed__(self):
        return self._data[::-1]

    def __setitem__(self, key, value):
        self._data[key] = value
        self.unsaved_changes = True

    def __str__(self):
        return '{},  unsaved changes: {}'.format(self._data, self.unsaved_changes)

    def add(self, other):
        self.__iadd__(other)

    def append(self, item):
        self._data.append(item)
        self.unsaved_changes = True
        self.check_length()

    def check_length(self):
        """removes entries from the beginning if maximal length is exceeded"""
        if self.max_length:
            self._data = self._data[-self.max_length:]

    def extend(self, other):
        self.__iadd__(other)

    def pop(self, index=-1):
        self._data.pop(index)
        self.unsaved_changes = True

    def remove(self, item):
        self._data.remove(item)
        self.unsaved_changes = True

    def update(self, data):
        """replaces data in the list"""
        self._data = data
        self.unsaved_changes = True
        self.check_length()
