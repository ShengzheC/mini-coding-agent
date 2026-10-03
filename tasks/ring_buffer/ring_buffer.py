"""Fixed-capacity FIFO queue, as used for firmware command queues."""


class RingBuffer:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._buf = [None] * capacity
        self._head = 0  # index of the oldest item
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def is_full(self) -> bool:
        return self._size == len(self._buf)

    def push(self, item) -> None:
        if self.is_full():
            raise OverflowError("ring buffer is full")
        tail = (self._head + self._size) % len(self._buf)
        self._buf[tail] = item
        self._size += 1

    def pop(self):
        if self._size == 0:
            raise IndexError("pop from an empty ring buffer")
        item = self._buf[self._head]
        self._buf[self._head] = None
        self._head = self._head + 1
        self._size -= 1
        return item

    def peek(self):
        if self._size == 0:
            raise IndexError("peek at an empty ring buffer")
        return self._buf[self._head]
