import pytest

from ring_buffer import RingBuffer


def test_fifo_order():
    rb = RingBuffer(3)
    for item in "abc":
        rb.push(item)
    assert [rb.pop(), rb.pop(), rb.pop()] == ["a", "b", "c"]


def test_full_and_empty_errors():
    rb = RingBuffer(2)
    rb.push(1)
    rb.push(2)
    assert rb.is_full()
    with pytest.raises(OverflowError):
        rb.push(3)
    rb.pop()
    rb.pop()
    with pytest.raises(IndexError):
        rb.pop()


def test_wraps_around_many_times():
    rb = RingBuffer(4)
    pushed, popped = [], []
    for i in range(50):
        rb.push(i)
        pushed.append(i)
        if len(rb) == 3:
            popped.append(rb.pop())
    while len(rb):
        popped.append(rb.pop())
    assert popped == pushed


def test_peek_does_not_remove():
    rb = RingBuffer(2)
    rb.push("cmd0")
    rb.push("cmd1")
    rb.pop()
    rb.push("cmd2")
    assert rb.peek() == "cmd1"
    assert len(rb) == 2
