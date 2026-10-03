from crc8 import crc8


def test_standard_check_value():
    assert crc8(b"123456789") == 0xF4


def test_empty_input_returns_init():
    assert crc8(b"") == 0x00
    assert crc8(b"", init=0xFF) == 0xFF


def test_single_bytes():
    assert crc8(b"\x00") == 0x00
    assert crc8(b"\x01") == 0x07
    assert crc8(b"\x80") == 0x89


def test_result_fits_in_a_byte():
    assert 0 <= crc8(bytes(range(256))) <= 0xFF


def test_detects_a_single_bit_flip():
    frame = bytearray(b"firmware-header-v3")
    good = crc8(bytes(frame))
    frame[5] ^= 0x10
    assert crc8(bytes(frame)) != good
