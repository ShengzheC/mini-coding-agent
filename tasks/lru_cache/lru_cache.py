"""A least-recently-used cache with a fixed capacity."""

from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._items: OrderedDict = OrderedDict()  # least recently used first

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key) -> bool:
        return key in self._items

    def get(self, key, default=None):
        """Return the cached value and mark the key as most recently used."""
        if key not in self._items:
            return default
        return self._items[key]

    def put(self, key, value) -> None:
        """Insert or update a key, evicting the least recently used key when over capacity."""
        if key in self._items:
            self._items.move_to_end(key)
        self._items[key] = value
        if len(self._items) > self.capacity:
            self._items.popitem(last=False)
