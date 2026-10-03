import pytest

from wear_leveling import pick_block


def test_lowest_erase_count_wins():
    assert pick_block({1: 10, 2: 3, 3: 7}, {1, 2, 3}) == 2


def test_only_free_blocks_are_considered():
    assert pick_block({1: 10, 2: 3, 3: 7}, {1, 3}) == 3


def test_unknown_blocks_count_as_never_erased():
    assert pick_block({1: 4, 2: 4}, {1, 2, 9}) == 9


def test_ties_go_to_the_lowest_block_id():
    assert pick_block({5: 2, 7: 2, 9: 2}, {9, 7, 5}) == 5


def test_no_free_blocks():
    with pytest.raises(ValueError):
        pick_block({1: 1}, set())
