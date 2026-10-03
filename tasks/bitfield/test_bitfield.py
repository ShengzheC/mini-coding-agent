import pytest

from bitfield import get_field, set_field


def test_get_field():
    assert get_field(0xABCD1234, 8, 8) == 0x12
    assert get_field(0xABCD1234, 28, 4) == 0xA


def test_set_field_keeps_other_bits():
    assert set_field(0xFFFFFFFF, 4, 4, 0x0) == 0xFFFFFF0F
    assert set_field(0x00000000, 4, 4, 0xA) == 0x000000A0
    assert set_field(0x12345678, 16, 8, 0xEE) == 0x12EE5678


def test_round_trip_of_packed_fields():
    reg = 0
    reg = set_field(reg, 0, 3, 5)
    reg = set_field(reg, 3, 5, 17)
    reg = set_field(reg, 8, 1, 1)
    assert (get_field(reg, 0, 3), get_field(reg, 3, 5), get_field(reg, 8, 1)) == (5, 17, 1)


def test_rejects_values_that_do_not_fit():
    with pytest.raises(ValueError):
        set_field(0, 0, 3, 8)
