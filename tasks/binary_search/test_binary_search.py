import bisect
import random

from binary_search import lower_bound


def test_existing_value():
    assert lower_bound([1, 3, 5, 7], 5) == 2


def test_first_of_duplicates():
    assert lower_bound([1, 2, 2, 2, 3], 2) == 1


def test_between_values():
    assert lower_bound([10, 20, 30], 25) == 2


def test_smaller_than_all():
    assert lower_bound([10, 20, 30], 5) == 0


def test_larger_than_all():
    assert lower_bound([10, 20, 30], 99) == 3


def test_empty_list():
    assert lower_bound([], 1) == 0


def test_matches_bisect_left_on_random_inputs():
    rng = random.Random(0)
    for _ in range(200):
        items = sorted(rng.randint(0, 20) for _ in range(rng.randint(0, 12)))
        target = rng.randint(-2, 22)
        assert lower_bound(items, target) == bisect.bisect_left(items, target)
